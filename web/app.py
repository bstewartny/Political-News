import tornado.ioloop
import tornado.web
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

	def search(self,query):
		client=solr.Solr(SOLR_URL)
                            
                searchleft=solr.SearchHandler(client,'/searchleft')
                searchright=solr.SearchHandler(client,'/searchright')

		# get left wing results
                left_results=searchleft(query)
                
                # get right wing results
                right_results=searchright(query)
                
		# merge highlights
                #merge_highlights(left_results,['summary','title'])
	        #merge_highlights(right_results,['summary','title'])
	
                facets=[]

                facet_fields=left_results.facet_counts['facet_fields']
  
                left_facet={}
                if 'entity' in facet_fields:
                  left_facets=facet_fields['entity']

                facet_fields=right_results.facet_counts['facet_fields']
  
                right_facet={}
                if 'entity' in facet_fields:
                  right_facets=facet_fields['entity']

                for key,value in left_facets.iteritems():
                  if key in right_facets:
                    right_facets[key]=right_facets[key]+value
                  else:
                    right_facets[key]=value

                facets=sorted(right_facets.iteritems(),key=operator.itemgetter(1))
                facets.reverse()

                facets=[n for (n,v) in facets]

                return {'left':left_results,'right':right_results,'facets':facets}

def merge_highlights(results,fieldnames):
	# merge highlights
        for doc in results.results:
                  docid=doc['id']
                  # find highlights
                  if docid in results.highlighting:
                          for fieldname in fieldnames:
                                  if fieldname in results.highlighting[docid]:
                                          segments=results.highlighting[docid][fieldname]
                                          highlight=''
                                          for segment in segments:
                                                  highlight=highlight+' '+segment
                                          highlight=highlight.strip()
                                          if len(highlight)>0 and not highlight[-1] in '.?!"\')':
                                                  highlight=highlight+'...'
                                          if len(highlight)>0 and not highlight[0] in 'abcdefghijklmnopqrstuvwxyz("\'':
                                                  highlight='...'+highlight
                                          doc[fieldname]=highlight


def create_id_slug(s):
	# strip out non-url and non-lucene friendly stuff...
	
	bad_chars="'+-&|!(){}[]^\"~*?:\\"
	s=s.strip()
	s=s.replace('http://','')
	s=s.replace('https://','')
	for c in bad_chars:
		s=s.replace(c,'_')
	
	while '__' in s:
		s=s.replace('__','_')
	
	return s	
	
class AutoSuggestHandler(tornado.web.RequestHandler):

  def get(self):
    prefix=self.get_argument('term','')
    client=solr.Solr(SOLR_URL)
    # get matching terms
    terms_client=solr.SearchHandler(client,'/terms')

    # return JSON
    results=terms_client(terms_regex=prefix+'.*')

    
    terms=results.terms['entity'].keys()

    terms.sort()

    json=[]
    for term in terms:
      json.append({'id':term,'label':term,'value':'"'+term+'"'})
    self.content_type = 'application/json'
    self.write(simplejson.dumps(json))

class MltHandler(tornado.web.RequestHandler):


	def mlt(self,itemid):
		client=solr.Solr(SOLR_URL)
	
		results=client.select('id:'+itemid,mlt='true',mlt_fl='text',mlt_count=20,mlt_minwl=3,mlt_mintf=2,mlt_mindf=2)
		
		mlt={}		

		if (results.results)>0:
			mlt['item']=results.results[0]
		else:
			mlt['item']={'title':itemid,'wing':'NA'}

		if itemid in results.moreLikeThis:
			tmp = results.moreLikeThis[itemid]
			# get right wing
			mlt['right']=filter(lambda x:x['wing']=='right',tmp)
			# get left wing
			mlt['left']=filter(lambda x:x['wing']=='left',tmp)

		return mlt


	def get(self):
			
		itemid=self.get_argument('id')
		itemid=create_id_slug(itemid)
		# find more like this...
		
		results=self.mlt(itemid)
		
		self.render('templates/mlt.html',itemid=itemid,item=results['item'],results=results)



application = tornado.web.Application([
                                        (r"/", SearchHandler),
                                        (r"/search",SearchHandler),
                                        (r"/mlt",MltHandler),
                                        (r"/autosuggest",AutoSuggestHandler)],
                                        static_path=os.path.join(os.path.dirname(__file__),"static")
                                        )

if __name__ == "__main__":
	application.listen(8888)
	tornado.ioloop.IOLoop.instance().start()
