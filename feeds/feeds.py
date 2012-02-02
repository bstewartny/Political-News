from BeautifulSoup import BeautifulSoup
import feedparser
import solr
import time
import datetime
import feeddefs
import urllib2
import re
from readability.readability import Document 
import subprocess
import nltk
import pytz

INDEX_URL='http://localhost:8983/solr'

index=solr.Solr(INDEX_URL)

Newlines = re.compile(r'[\r\n]\s+')

def extract_entity_names(t):
    entity_names = []
    
    if hasattr(t, 'node') and t.node:
        if t.node == 'NE':
            entity_names.append(' '.join([child[0] for child in t]))
        else:
            for child in t:
                entity_names.extend(extract_entity_names(child))
                
    return entity_names
 
def is_substr(s,a):
  s=s.lower()
  for t in a:
    if len(t)<len(s):
      break
    else:
      t=t.lower()
      if not t==s:
        if t.startswith(s) or t.endswith(s):
          return True
  return False

def unique_entities(a):
  u=[]
  a=list(set(a))

  # remove any single-word entities (too ambiguous in most cases)
  a=[s for s in a if len(s.split())>1]
  # remove any entities more than 3 words
  a=[s for s in a if len(s.split())<4]
  # TODO: remove entities where any of the words are noise words, and also filter out some standard phrases:
  # "Written By", "Continue Reading", etc.

  a.sort(lambda x,y:cmp(len(y),len(x)))

  return [x for x in a if not is_substr(x,a)]

def get_entities(text):
  sentences = nltk.sent_tokenize(text)
  tokenized_sentences = [nltk.word_tokenize(sentence) for sentence in sentences]
  tagged_sentences = [nltk.pos_tag(sentence) for sentence in tokenized_sentences]
  chunked_sentences = nltk.batch_ne_chunk(tagged_sentences, binary=True)
  
  entity_names=[]
  for tree in chunked_sentences:
    entity_names.extend(extract_entity_names(tree))

  return unique_entities(entity_names)

def get_text_lynx(data):
    try:
        return subprocess.Popen(['/usr/local/bin/lynx', 
                      '-assume-charset=UTF-8', 
                      '-display-charset=UTF-8', 
                      '-dump', 
                      '-stdin'], 
                      stdin=subprocess.PIPE, 
                      stdout=subprocess.PIPE).communicate(input=data.encode('utf-8'))[0].decode('utf-8')
    except:
          print 'error getting text from lynx'
    return ''

def get_page_text(url):
	txt=''
        data=None
	try:
		# given a url, get page content
		data = urllib2.urlopen(url).read()
		
                if not data is None:
		  return strip_html_tags(Document(data).summary())
	except:
		print 'error getting text from url: '+url
                if not data is None:
                  return get_text_lynx(data)
	return txt

def create_id_slug(s):
	# strip out non-URL and non-Lucene friendly stuff...
	bad_chars="'+-&|!(){}[]^\"~*?:\\"
	s=s.strip()
	s=s.replace('http://','')
	s=s.replace('https://','')
	for c in bad_chars:
		s=s.replace(c,'_')
	
	while '__' in s:
		s=s.replace('__','_')
	
	return s	

def strip_html_tags(html):
	# just get appended text elements from HTML
        try:
          text="".join(BeautifulSoup(html,convertEntities=BeautifulSoup.HTML_ENTITIES).findAll(text=True))
	  return text
        except:
          print 'Failed to strip html tags...'
          return html

def get_attribute(item,names):
	for name in names:
		if name in item:
			return item[name]
	return None

utc=pytz.utc

def get_item_date(item):
	#return None
	d=get_attribute(item,['published_parsed','updated_parsed','created_parsed','date_parsed'])
	if not d is None:
		try:
                  print 'got date attribute: '
                  print d
                  dt=datetime.datetime.fromtimestamp(time.mktime(d))
                  dt=dt.replace(tzinfo=utc)
                  #dt=dt.astimezone(utc)

		  print 'parsed date:'
                  print dt
                  return dt
                except:
		  return None
	return None	

def analyze_feed_item(item):
	
	# strip HTML tags from summary/description
	summary=get_attribute(item,['summary','description'])
	
	if not summary is None:
		summary=strip_html_tags(summary)
		item["summary"]=summary
	

	link=item['link']
	if len(link)>0:
		print 'Get extracted text: '+link
		text=get_page_text(link)
		if len(text)>len(summary):
			item["summary"]=text
                
        text=item['summary']

        if len(text)>0:
          print 'get entities...'
          entity_names=get_entities(text)
          item['entity']=entity_names 


        clusterid=get_cluster(item)
        if not clusterid is None:
          if len(clusterid)>0:
            item['clusterid']=clusterid

	return item

def compute_similarity(a,b):
  return 0

def find_similar(query):
  return []

def get_cluster(item):
  min_sim=20.0

  # get features from item
  
  # form query using features
  query='+contents:('
  text=item['title'] + ' ' + item['summary']
  for word in text.split():
    query+=' '+word+' '
  query+=')'

  # find similar items in index
  similar_items=find_similar(query)

  max_sim=0
  max_sim_item=None
  # compute similarity to items

  for sim_item in similar_items:
    sim=compute_similarity(item,sim_item)
    if sim >= min_sim and sim > max_sim:
      max_sim=sim
      max_sim_item=sim_item
  
  # pick most similar item and get that cluster id
  if max_sim>=min_sim and max_sim_item is not None:
    return max_sim_item['clusterid']
  else:
    return None

def get_solr_doc(item):
	doc={}
	doc["title"]=item["title"]
	doc["summary"]=item["summary"]
	d=get_item_date(item)
	if not d is None:
		doc["date"]=d
	if 'author' in item:
		doc['author']=item['author']
	doc['feed']=item['feed']
	doc['feedlink']=item['feedlink']
	#doc["date"]=item["date"]
	doc["wing"]=item["wing"]
	doc["link"]=item["link"]
        if 'entity' in item:
            doc['entity']=item['entity']

	doc["id"]=create_id_slug(get_attribute(doc,["link","title"]))

	return doc

def index_doc(doc):
	# send document to solr
	retries=0
       
	while retries<3:
		try:
			index.add(doc,commit=False)
			break
		except Exception as e:
                        print e
			print 'indexing failed...'
			time.sleep(1)
			retries=retries+1
			if retries<3:
				print 'retrying...'
			else:
				print 'retries failed.'


def index_commit():
	index.commit()

def process_feeds(feeds):
	total=0
	print 'processing '+str(len(feeds))+' feeds...'
	for feed in feeds:
		print 'processing '+feed['wing'] +' wing feed: '+feed['name'] +'...'
		rss=feedparser.parse(feed['rss'])
		count=0
		for item in rss["items"]:
			item["wing"]=feed['wing']
			item['feed']=feed['name']
			item['feedlink']=feed['link']
			if 'author' in feed:
				item['author']=feed['author']
			item=analyze_feed_item(item)
			doc=get_solr_doc(item)
			index_doc(doc)
			count=count+1
			if count % 10 ==0:
				index_commit()
		print 'processed '+str(count)+' items from feed.'
		total=total+count
	
	index_commit()
	print 'processed '+str(total)+' total items.'


if __name__ == "__main__":
	process_feeds(feeddefs.feeds)

