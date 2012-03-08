import tornado.ioloop
import tornado.web
import feeds
import solr
import os
from tornado.template import Template
import simplejson
import operator

SOLR_URL='http://localhost:8983/solr'

class SearchHandler(tornado.web.RequestHandler):
  
  def get(self):
    query=self.get_argument('q','')
    results=self.search(query)	
    self.render('templates/index.html',query=query,results=results)

  def clean_results_summaries(self,results):
    return [self.clean_result_summary(result) for result in results.results]

  def clean_result_summary(self,result):
    result['clean_summary']=feeds.clean_summary(result['summary'])
    return result

  def get_top_result(self,query):
    client=solr.Solr(SOLR_URL) 
    topsearch=solr.SearchHandler(client,'/searchtop')
    topsearch_results=topsearch(query)
    if len(topsearch_results.results)>0:
      return self.clean_result_summary(topsearch_results.results[0])
    else:
      return None

  def get_entities(self,query):
    client=solr.Solr(SOLR_URL) 
    entitysearch=solr.SearchHandler(client,'/entities')
    entity_results=entitysearch(query)
    return []
    #return [key for key,value in entity_results.facet_counts['facet_fields']['entity'].iteritems()]
    
    #entities=[]

    #if 'entity' in entity_results.facet_counts['facet_fields']:
    #  for key,value in entity_results.facet_counts['facet_fields']['entity'].iteritems():
    #    entities.append(key)

    #return entities

  def search(self,query):
    client=solr.Solr(SOLR_URL)
    searchleft=solr.SearchHandler(client,'/searchleft')
    searchright=solr.SearchHandler(client,'/searchright')
    top_result=self.get_top_result(query)
    # exclude top result from other searches (not working now for some reason)
    fq=None
    if top_result is not None:
      fq="-id:"+top_result['id']
    # get left wing results
    if fq is not None:
      left_results=self.clean_results_summaries(searchleft(query,fq=fq))
    else:
      left_results=self.clean_results_summaries(searchleft(query))
    # get right wing results 
    if fq is not None:
      right_results=self.clean_results_summaries(searchright(query,fq=fq))
    else:
      right_results=self.clean_results_summaries(searchright(query))
    # get top facets over all docs to show left-hand side topics
    facets=self.get_entities('*:*') 
    result= {'left':left_results,'right':right_results,'facets':facets}
    if top_result is not None:
      result['top']=top_result
    return result

def create_id_slug(s):
  # strip out non-url and non-lucene friendly stuff...
  bad_chars="'+-&|!(){}[]^\"~*?:\\"
  s=s.strip().replace('http://','').replace('https://','')
  for c in bad_chars:
    s=s.replace(c,'_')
  while '__' in s:
    s=s.replace('__','_')
  return s	
	
class AutoSuggestHandler(tornado.web.RequestHandler):

  def get(self):
    prefix=self.get_argument('term','')
    client=solr.Solr(SOLR_URL)
    terms_client=solr.SearchHandler(client,'/terms')
    results=terms_client(terms_regex=prefix+'.*')
    json=[{'id':term,'label':term,'value':'"'+term+'"'} for term in sorted(results.terms['entity'].keys())]
    self.content_type = 'application/json'
    self.write(simplejson.dumps(json))

application = tornado.web.Application([
              (r"/", SearchHandler),
              (r"/search",SearchHandler),
              (r"/autosuggest",AutoSuggestHandler)],
              static_path=os.path.join(os.path.dirname(__file__),"static")
              )

if __name__ == "__main__":
  application.listen(8888)
  tornado.ioloop.IOLoop.instance().start()
