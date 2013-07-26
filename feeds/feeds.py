from BeautifulSoup import BeautifulSoup
import feedparser
import solr
import time
import datetime
import feeddefs
#import urllib2
import urllib3
import entities

import re
#from readability.readability import Document 
import subprocess
import nltk
import pytz
from threading import Thread


http=urllib3.PoolManager()

INDEX_URL='http://localhost:8983/solr'

index=solr.Solr(INDEX_URL)

invalid_entities=['tweet text',
    'daily beast','javascript tag','trademark accessibility','white house','continue reading','written by','united states',
    'new york','new york city','new york times','washington post',
    'raw story','fox news','associated press','wall street','wall street journal','weekly standard']

invalid_entities.extend([feed['feed'].lower() for feed in feeddefs.feeds])

entity_map={}

def matches_entity(text,entity):
    text=' '+text.lower()+' '
    for pattern in entity['patterns']:
        if text.find(' '+pattern.lower()+' ')>-1:
            return True
    return False

def get_entities(text):
    found=[]
    for entity in entities.whitelist:
        if matches_entity(text,entity):
            found.append(entity['name'])
    
    found.extend(get_entities3(text))
    return found

def extract_entity_names(t):
  entity_names = []
  if hasattr(t, 'node') and t.node:
      if t.node == 'NE':
          entity_names.append(' '.join([child[0] for child in t]))
      else:
          for child in t:
              entity_names.extend(extract_entity_names(child))
              
  return entity_names

def is_substr(s,t):
  if len(t)<len(s):
    return False
  else:
    t=t.lower()
    return ((not t==s) and (t.startswith(s) or t.endswith(s)))

def has_substr(s,a):
  s=s.lower()
  for t in a:
    if is_substr(s,t):
      return True
  return False

def all_caps(s):
    return s.upper()==s

def filter_entities(a):
  u=[]
  a=list(set(a))
  # remove any single-word entities (too ambiguous in most cases)
  a=[s for s in a if len(s.split())>1]
  # remove any entities more than 2 words
  a=[s for s in a if len(s.split())<3]
  # remove any entities that are all CAPS
  a=[s for s in a if not all_caps(s)]
  a.sort(lambda x,y:cmp(len(y),len(x)))
  a=[x for x in a if not has_substr(x,a)]
  a=[s for s in a if not s.lower() in invalid_entities]
  
  return a


def get_entities2(text):
    print 'get_entities: '+text
    entities=[]
    for sent in nltk.sent_tokenize(text):
        for chunk in nltk.ne_chunk(nltk.pos_tag(nltk.word_tokenize(sent))):
            if hasattr(chunk, 'node'):
                names=extract_entity_names(chunk)
                if len(names)>0:
                    print names
                    entities.extend(names)
                        
                #print chunk.node, ' '.join(c[0] for c in chunk.leaves())
                #entities.append(' '.join(c[0] for c in chunk.leaves()))
    return filter_entities(entities)

def get_entities3(text):
  sentences = nltk.sent_tokenize(text)
  tokenized_sentences = [nltk.word_tokenize(sentence) for sentence in sentences]
  tagged_sentences = [nltk.pos_tag(sentence) for sentence in tokenized_sentences]
  chunked_sentences = nltk.batch_ne_chunk(tagged_sentences, binary=True)
  
  entity_names=[]
  for tree in chunked_sentences:
    entity_names.extend(extract_entity_names(tree))

  return filter_entities(entity_names)

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
    print 'Get url:',url
    r=http.request('GET',url)
    data=r.data
    #data = urllib2.urlopen(url).read()
    if not data is None and len(data)>0:
      summary=data #Document(data).summary()
      return strip_html_tags(summary)
  except:
    print 'error getting text from url: '+url
    if not data is None and len(data)>0:
      return get_text_lynx(data)
  return txt

bad_chars="'+-&|!(){}[]^\"~*?:\\"

def replace_bad_chars(s):
  for c in bad_chars:
    s=s.replace(c,'_')
  return s

def compress_underscores(s):
  while '__' in s:
    s=s.replace('__','_')
  return s

slug_pattern=re.compile('[\W_]+')

def create_slug(s):
  # create url friendly name for source/topic name
  return slug_pattern.sub('',s)

def create_id_slug(s):
  # strip out non-URL and non-Lucene friendly stuff...
  return compress_underscores(replace_bad_chars(s.strip().replace('http://','').replace('https://','')))	

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
  d=get_attribute(item,['published_parsed','updated_parsed','created_parsed','date_parsed'])
  if not d is None:
    try:
      return datetime.datetime.fromtimestamp(time.mktime(d)).replace(tzinfo=utc)
    except:
      return None
  return None

max_summary_len=400
min_sentence_len=20
max_sentence_len=300
min_clean_words=6
min_clean_words_ratio = 0.8
min_word_len=2
max_word_len=25

def clean_sentence(sent):
  # remove date line
  # TODO: also look for unicode 'long dash' here...
  m=re.match('^.+--\s',sent)
  if m is not None:
    sent=sent[m.end():]
  return sent

def is_clean_word(word):
  if len(word)>max_word_len:
    return False
  if len(word)<min_word_len:
    return False
  if re.match('^[a-z]+$',word) is None and re.match('^[A-Z][a-z]+$',word) is None:
    return False
  return True

def is_clean_sentence(sent):
  if len(sent) < min_sentence_len:
    return False
  if len(sent) > max_sentence_len:
    return False
  if not sent[0].upper()==sent[0]:
    return False
  if not sent[-1]=='.':
    return False
  words=nltk.word_tokenize(sent)
  num_clean_words=len(filter(is_clean_word,words))
  if num_clean_words < min_clean_words:
    return False
  if float(num_clean_words) / float(len(words)) < min_clean_words_ratio:
    return False
  return True

def clean_summary(summary):
  # get one or two very clean sentences from the text
  if summary is None:
    return None
  if len(summary)==0:
    return None
  clean_sentences=[]
  total_len=0
  summary=summary.replace('&apos;','\'')
  for sentence in filter(is_clean_sentence,map(clean_sentence,nltk.sent_tokenize(summary))):
    if total_len+len(sentence) > max_summary_len and len(clean_sentences)>0:
      return ' '.join(clean_sentences)
    else:
      clean_sentences.append(sentence)
      total_len=total_len+len(sentence)
  
  if len(clean_sentences)>0:
    return ' '.join(clean_sentences)
  else:
    if len(summary)>200:
      return summary[:200]+'...'
    else:
      return summary

def analyze_feed_item(item):
	
  # strip HTML tags from summary/description
  summary=get_attribute(item,['summary','description'])
  
  if not summary is None:
    summary=strip_html_tags(summary)
    item["summary"]=clean_summary(summary)

  link=item['link']
  text=summary
  #if len(link)>0:
  #  print 'Get extracted text: '+link
  #  text=get_page_text(link)
  #  if text is None or len(summary)>len(text):
  #    text=summary
  #  item["body"]=text
  #else:
  item["body"]=summary

  if item["summary"] is None or len(item["summary"])==0:
    item["summary"]=clean_summary(text)
    
  text = item["title"] 
  print text
  entities=get_entities(text)
  if len(entities)>0:
      print entities
  item['entity']=entities
  item['entitykey']=[create_slug(entity) for entity in entities]
  return item

def copy_attribute(source,dest,name):
  if name in source:
    if not name in dest:
      dest[name]=source[name]

def copy_attributes(source,dest,names):
  for name in names:
    copy_attribute(source,dest,name)

def create_solr_doc(item):
  doc={}
  copy_attributes(item,doc,['title','summary','body','author','feed','feedlink','wing','link','entity','entitykey'])
  d=get_item_date(item)
  doc['feedkey']=create_slug(doc['feed'])
  if d is not None:
    doc["date"]=d
  doc["id"]=create_id_slug(get_attribute(doc,["link","title"]))
  return doc

def index_doc(doc):
  index.add(doc,commit=False)

def index_error_queue():
  for doc in queue:
    index.add(doc,commit=False)

def index_commit():
  index.commit()

def process_item(feed,item):
  copy_attributes(feed,item,['wing','feed','name','rss','link','author'])
  index_doc(create_solr_doc(analyze_feed_item(item)))

def process_feed(feed):
  print 'processing '+feed['wing'] +' wing feed: '+feed['feed'] +'...'
  rss=feedparser.parse(feed['rss'])
  count=0
  for item in rss["items"]:
    process_item(feed,item)
    count=count+1
    if count % 10 ==0:
      index_commit()
  print 'processed '+str(count)+' items from feed.'
  return count

def process_feeds(feeds):
  total=0
  print 'processing '+str(len(feeds))+' feeds...'
  for feed in feeds:
    total=total+process_feed(feed)
  
  index_commit()
  print 'processed '+str(total)+' total items.'


num_threads=4

if __name__ == "__main__":
  feeds=feeddefs.feeds

  process_feeds(feeds)
  
  #batch_size=len(feeds)/num_threads
  #
  #threads=[]
  #for i in range(0,num_threads):
  #  batch=feeds[i*batch_size:(i*batch_size)+batch_size]
  #  thread=Thread(target=process_feeds,args=(batch,))
  #  thread.start()
  #  threads.append(thread)


