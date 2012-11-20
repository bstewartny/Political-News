import tornado.ioloop
import tornado.web
import feeds
import solr
import os
from tornado.template import Template
import simplejson
import operator
import nltk

SOLR_URL='http://localhost:8983/solr'
client=solr.Solr(SOLR_URL) 

def get_handler(name):
  return solr.SearchHandler(client,name)

def clean_results_summaries(results):
  return [clean_result_summary(result) for result in results.results]

def clean_result_summary(result):
  result['clean_summary']=feeds.clean_summary(result['summary'])
  return result

def get_topic_sources(topickey):
  return []

def get_topic_topics(topickey):
  return []

def get_topic_headlines(topickey):
    r=search(None,topickey,None,None)
    return r['results']

def get_topics():
  entitysearch=get_handler('/entities')
  entity_results=entitysearch('*:*')
  # for each entity, get top sources...
  return [{'name':key,'key':feeds.create_slug(key),'sources':get_topic_sources(feeds.create_slug(key)),'topics':get_topic_topics(feeds.create_slug(key)),'results':get_topic_headlines(feeds.create_slug(key))} for key,value in entity_results.facet_counts['facet_fields']['entity'].iteritems()]

def get_sources():
  return []

def get_entities(query):
  entitysearch=get_handler('/entities')
  entity_results=entitysearch(query)
  return [key for key,value in entity_results.facet_counts['facet_fields']['entity'].iteritems()]

def get_feeds(query):
  feedssearch=get_handler('/feeds')
  feeds_results=feedssearch(query)
  return [key for key,value in feeds_results.facet_counts['facet_fields']['feed'].iteritems()]

def search(breadcrumbs,topic,source,query):
  facets=get_entities('*:*')
  sources=get_feeds('*:*')
  search_handler=get_handler('/select')
  
  if (query is None or len(query)==0) and (topic is None) and (source is None):
      # do a default search over the top 3 topics so we show some new/popular items instead of just random items
      if len(facets)>0:
        query='"' + '" OR "'.join(facets[:3])+'"'
  
  if (topic is not None) or (source is not None):
    if len(query)>0:
      query='+'+query
    if topic is not None:
      query=query + ' +entitykey:'+topic
    if source is not None:
      query=query + ' +feedkey:'+source

  results=clean_results_summaries(search_handler(query))

  topics=[{'name':facet,'key':feeds.create_slug(facet)} for facet in facets]
  sources=[{'name':source,'key':feeds.create_slug(source)} for source in sources]

  tagcloud=[{'text':word,'freq':freq,'link':'?q='+word} for (word,freq) in get_top_words(results)]
 
  return {'results':results,'tagcloud':tagcloud,'topics':topics,'sources':sources,'breadcrumbs':breadcrumbs}

# setup stop words map using common english words and some other noise...
stop_words_array="how,can,corp,inc,llp,llc,inc,v,v.,vs,vs.,them,he,she,it,where,with,now,legal,can,how,new,may,from,not,did,you,does,any,why,your,are,llp,corp,inc,a,an,and,are,as,at,be,but,by,for,if,in,into,is,it,no,not,of,on,or,such,that,the,their,then,there,these,they,this,to,was,will,with"

stop_words={}

for word in stop_words_array.split(','):
  stop_words[word]=word

for word in nltk.corpus.stopwords.words('english'):
  stop_words[word]=word

def is_noise_word(word):
    # not ENG noise word
    # must be alpha
    # not too short
    # not too long
    return (word in stop_words) or ( not (word.isalpha() and len(word)>2 and len(word)<20))

def get_result_words(result):
    words={}
    title=result['title']
    summary=result['clean_summary']
    for word in nltk.word_tokenize((title+summary).lower()):
        if not is_noise_word(word):
            print 'not a noise word: "'+word+'"'
            if word in words:
                words[word]=words[word]+1
            else:
                words[word]=1
    return words

MAX_TOP_WORDS=60

def get_top_words(results):
    words={}
    for result in results:
        result_words=get_result_words(result)
        for (word,freq) in result_words.iteritems():
            if word in words:
                words[word]=words[word]+freq
            else:
                words[word]=freq
    
    b=[(v,k) for (k,v) in words.iteritems()]
    b.sort()
    b.reverse()
    
    b=[(k,v) for (v,k) in b[:MAX_TOP_WORDS]]
    b.sort()
    return b

class SearchHandler(tornado.web.RequestHandler):
  
  def get(self,args):
    
    query=self.get_argument('q','')
    
    source=None
    
    topic=None
    
    parts=args.split('/')
    
    if len(parts)>1:
      if parts[0]=='topic':
        topic=parts[1]
        if len(parts)==4:
          source=parts[3]
      elif parts[0]=='source':
        source=parts[1]
        if len(parts)==4:
          topic=parts[3]
  
    breadcrumbs=[]
    if len(parts)>1:
      breadcrumbs.append({'name':parts[1],'link':'/'+parts[0]+'/'+parts[1],'active':False})
      if len(parts)==4:
        breadcrumbs.append({'name':parts[3],'link':'/'+parts[0]+'/'+parts[1]+'/'+parts[2]+'/'+parts[3],'active':False})
    if len(query)>0:
      breadcrumbs.append({'name':query,'link':self.request.uri,'active':False})

    if len(breadcrumbs)>0:
      breadcrumbs[len(breadcrumbs)-1]['active']=True


    results=search(breadcrumbs,topic,source,query)
    self.render('templates/index.html',query=query,results=results)




class TopicsHandler(tornado.web.RequestHandler):

  def get(self):
    topics=get_topics()
    self.render('templates/topics.html',topics=topics)

class SourcesHandler(tornado.web.RequestHandler):

  def get(self):
    sources=get_sources()
    self.render('templates/sources.html',sources=sources)

class AutoSuggestHandler(tornado.web.RequestHandler):

  def get(self):
    prefix=self.get_argument('term','')
    terms_client=get_handler('/terms')
    results=terms_client(terms_regex=prefix+'.*')
    json=[{'id':term,'label':term,'value':'"'+term+'"'} for term in sorted(results.terms['entity'].keys())]
    self.content_type = 'application/json'
    self.write(simplejson.dumps(json))

class TypeAheadHandler(tornado.web.RequestHandler):

  def get(self):
    prefix=self.get_argument('query','')
    terms_client=get_handler('/terms')
    results=terms_client(terms_regex=prefix+'.*')
    terms=sorted(results.terms['entity'].keys())
    self.set_header("Content-Type", "application/json") 
    self.write({'options':terms})
    self.finish()

#static_path=os.path.join(os.path.dirname(__file__),"static")
application = tornado.web.Application([
              (r"/autosuggest",AutoSuggestHandler),
              (r"/typeahead",TypeAheadHandler),
              (r"/topics",TopicsHandler),
              (r"/sources",SourcesHandler),
              (r"/(.*)", SearchHandler)],
              static_path='/Users/bstewart/Political-News/web/static/'
              )

if __name__ == "__main__":
  application.listen(8888)
  tornado.ioloop.IOLoop.instance().start()
