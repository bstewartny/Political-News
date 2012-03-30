import tornado.ioloop
import tornado.web
import feeds
import solr
import os
from tornado.template import Template
import simplejson
import operator

SOLR_URL='http://localhost:8983/solr'
client=solr.Solr(SOLR_URL) 

def get_handler(name):
  return solr.SearchHandler(client,name)

def clean_results_summaries(results):
  return [clean_result_summary(result) for result in results.results]

def clean_result_summary(result):
  result['clean_summary']=feeds.clean_summary(result['summary'])
  return result

def get_top_result(query):
  topsearch=get_handler('/searchtop')
  topsearch_results=topsearch(query)
  if len(topsearch_results.results)>0:
    return clean_result_summary(topsearch_results.results[0])
  else:
    return None

def get_topic_sources(topickey):
  return []

def get_topic_topics(topickey):
  return []

def get_topics():
  entitysearch=get_handler('/entities')
  entity_results=entitysearch('*:*')
  # for each entity, get top sources...
  return [{'name':key,'key':feeds.create_slug(key),'sources':get_topic_sources(feeds.create_slug(key)),'topics':get_topic_topics(feeds.create_slug(key))} for key,value in entity_results.facet_counts['facet_fields']['entity'].iteritems()]

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
  searchleft=get_handler('/searchleft')
  searchright=get_handler('/searchright')
  
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

  left_results=clean_results_summaries(searchleft(query))
  right_results=clean_results_summaries(searchright(query))

  # interleave left and right results
  results=[y for x in map(None,left_results,right_results) for y in x if y]  

  topics=[{'name':facet,'key':feeds.create_slug(facet)} for facet in facets]
  sources=[{'name':source,'key':feeds.create_slug(source)} for source in sources]

 
  return {'results':results,'topics':topics,'sources':sources,'breadcrumbs':breadcrumbs}

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

application = tornado.web.Application([
              (r"/autosuggest",AutoSuggestHandler),
              (r"/topics",TopicsHandler),
              (r"/sources",SourcesHandler),
              (r"/(.*)", SearchHandler)],
              static_path=os.path.join(os.path.dirname(__file__),"static")
              )

if __name__ == "__main__":
  application.listen(8888)
  tornado.ioloop.IOLoop.instance().start()
