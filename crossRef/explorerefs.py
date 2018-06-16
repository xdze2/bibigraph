
import requests
import pickle
import time


cachefilename = "crossref_cache.pickle"

try:
    with open(cachefilename, 'rb') as f:
        requesteddoi = pickle.load(f)
except:
    requesteddoi = {}
    
print( len(requesteddoi), 'articles loaded from cache' )



def requestDoi(doi):
    """ Return the data for a given DOI
        - look first in the dictionary requesteddoi
        - if no data send the request to https://api.crossref.org/
    """
    if doi in requesteddoi:
        return requesteddoi[doi]
    else:
        url = 'https://api.crossref.org/works/'
        time.sleep(1)
        params = { 'mailto':'xdze2.me@gmail.com'}
        response = requests.get(url+doi, params=params)
        
        if not response.ok:
            print('query error')
            return None
        else:
            response = response.json()
            message = response['message']
            
            requesteddoi[doi] = message
            
            # save to file
            with open(cachefilename, 'wb') as f:
                pickle.dump(requesteddoi, f)
                
            return message

        
def getRefList(doi):
    """ Return the list of reference for which a doi is specified
        for the article doi
    """
    message = requestDoi(doi)
    references = message.get('reference', [])
    referencesWithDoi = { ref['DOI'] for ref in references if 'DOI' in ref }
    # print(doi, len(referencesWithDoi))
    return list( referencesWithDoi )


def printInfo(doi):
    """ Print info about a article
    """
    message = requestDoi(doi)
    doi = message['DOI']
    title = message.get('title', [''] )[0].split(' ')
    if len(title)>8:
        title.insert(8, '\n')
    title = ' '.join( title )
    
    authors = '; '.join( ['{given} {family}'.format( **auth ) for auth in message['author'] ] )
    year = message['issued']['date-parts'][0][0]
    print( "[{DOI}] {title}".format( DOI=message['DOI'], title=title ) )
    print(  authors, '-', message['container-title'][0], '-', year )
    print( 'nbr de refs: ', len(message.get('reference', []) ), '- with doi:', len(getRefList(doi)) )

    
    
def getRandomDOI( N=10 ):
    """ Obtain a random sampling from crossref
        of size N doi
    """
    url = 'https://api.crossref.org/works/'
    time.sleep(1)
    params = { 'mailto':'xdze2.me@gmail.com',
                'sample': str(N),
                'select':'DOI,title' }
    response = requests.get(url, params=params)
    response = response.json()
    
    response = response['message']['items']
    
    return [ (d['DOI'], d.get('title', '')) for d in response  ]


def getOneRandomDoi():
    """ to get one random doi number
    """
    r = getRandomDOI( N=1 )
    print( r[0][1] )
    return r[0][0]


# -- Graph part --

# pip install graphviz
# https://graphviz.readthedocs.io/en/stable/
# https://graphviz.gitlab.io/_pages/doc/info/attrs.html
from graphviz import Digraph
from IPython.display import Image, display, SVG

from collections import Counter

class Referencesgraph():
    """ Object to explore the reference graph
        starting from one article 
    """
    
    def __init__(self, doi):
        self.nodes = {doi:{ 'gen':0, 'citedBy':[] } }
        self.len = len( self.nodes )
    
    
    def grow(self):
        """ Expand the graph by including all the references papers
            i.e. expand one generation
        """
        nodes = self.nodes
        lastGen = self.lastGen()
        lastGenNodes = [ doi for doi, info in nodes.items() if info['gen']==lastGen ]
        
        for i, doi in enumerate( lastGenNodes ):
            print('{}/{} fetch %s'.format( i, len(lastGenNodes), doi ), end='\r')
            references = getRefList(doi)
            
            self.nodes[doi]['refs'] = references
            for ref in references:
                if ref not in self.nodes:
                    self.nodes[ref] = {'gen':lastGen+1, 'citedBy':[doi] }
                else:
                    self.nodes[ref]['citedBy'].append( doi )
                
        print('- done -' + ' '*10 )
        self.len = len( self.nodes )
                   
            
    def lastGen(self):
        """ Number of the last generation of the graph 
        """
        nodes = self.nodes
        return max( n['gen'] for n in nodes.values() )
    
    def printstats(self):
        print( 'nbre nodes: {}\nlast gen: {}'.format(self.len, self.lastGen() ) )
        
    
    def degree(self, node):
        return len( self.nodes[node].get('refs', []) ) + len( self.nodes[node].get('citedBy', []) )
        
        
    def nodesVisitedTwice(self, N = 3):
        """ List of nodes visited at least twice (N times)
            i.e. nodes with an out_degree >= N
        """
        isVisitedTwice = lambda node: len(node.get('citedBy', []))>=N
        return [ doi for doi, node in self.nodes.items() if isVisitedTwice(node) ]

        
    def nodesToDraw(self, N = 3 ):
        """ Keep the nodes only cited more than N times
            and rebuild the upward graph
        """
        nodesToCheck = self.nodesVisitedTwice(N=N)
        nodesToDraw = []
        linksToDraw = []
        while nodesToCheck:
            doi = nodesToCheck.pop()
            nodesToDraw.append(doi)

            for citing in self.nodes[doi]['citedBy']:

                linksToDraw.append( (doi, citing) )
                if citing not in nodesToDraw and citing not in nodesToCheck:
                    nodesToCheck.append( citing )

        return nodesToDraw, linksToDraw
        
        
    def builtGraphviz(self, N = 3 ):
        """ Use Graphviz to draw the graph
            return a graphviz object
            
            the color is the generation number
        """
        nodesToDraw, linksToDraw = self.nodesToDraw(N = N )
        
        colorGen = ['red', 'gold1', 'cyan3', 'darkorchid2', 'chartreuse2']
        # see https://graphviz.gitlab.io/_pages/doc/info/colors.html

        DG = Digraph(comment='hello', format='svg', engine='dot' , graph_attr={'size':'10' })#})'root':doi} )
        DG.graph_attr['rankdir'] = 'LR'

        for doi in nodesToDraw:
            info =  self.nodes[doi]
            DG.node(parsedoi(doi), color=colorGen[info['gen']], style='filled', label= buildlabel(doi))

        for source, target in linksToDraw:
            DG.edge(parsedoi(source), parsedoi(target))  

        return DG
        
        
    def mostCited(self):
        """ Shows the most cited articles in the graph
        """
        citedByCount = Counter( { doi:len(info['citedBy']) for doi, info in self.nodes.items() } )
        
        for doi, count in citedByCount.most_common(4):
            printInfo( doi )
            print('')
            
            
# -- graph plot --

def buildlabel(doi):
    """ Gives the label to show on the graph
    """
    info = requestDoi( doi )
    year = info['issued']['date-parts'][0][0]
    familyname = [ auth['family'] for auth in info['author'] if auth['sequence']=='first'][0]

    key = familyname+str(year)
    return key

def parsedoi(doi):
    # bug graphviz
    doi = doi.replace(':', '')
    return doi


