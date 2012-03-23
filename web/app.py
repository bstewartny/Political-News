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
    topsearch=get_handler('/searchtop')
    topsearch_results=topsearch(query)
    if len(topsearch_results.results)>0:
      return self.clean_result_summary(topsearch_results.results[0])
    else:
      return None

  def get_entities(self,query):
    entitysearch=get_handler('/entities')
    entity_results=entitysearch(query)
    return [key for key,value in entity_results.facet_counts['facet_fields']['entity'].iteritems()]
  
  def search(self,query):
    facets=self.get_entities('*:*') 
    searchleft=get_handler('/searchleft')
    searchright=get_handler('/searchright')
    
    if query is None or len(query)==0:
        if len(facets)>0:
          query='"' + '" OR "'.join(facets[:3])+'"'
    
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
    result= {'left':left_results,'right':right_results,'facets':facets}
    if top_result is not None:
      result['top']=top_result
    return result
	
class AutoSuggestHandler(tornado.web.RequestHandler):

  def get(self):
    prefix=self.get_argument('term','')
    terms_client=get_handler('/terms')
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
