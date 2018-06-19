import requests
import urllib.parse
import pickle
import time
import os


class MetaDataStore(dict):
    """ Store for the metadata 
        and interface to the Crossref API
    """
    
    def __init__(self, cachelocation = 'data/cachefile.pickle'):
        """ Load the cached metadata from the `cachelocation` filename
        """
        self.cachelocation = cachelocation
        self.mailadress = 'xdze2.me@gmail.com'
        
        try:
            with open(cachelocation, 'rb') as f:
                self.update( pickle.load(f) )
                
            print( len(self), 'metadata loaded from `%s`' % cachelocation )
        
        except FileNotFoundError:
            print( '`%s` not found. A new file will be created.' % cachelocation  )

            
    def import_pickle(path):
        """ Import the metadata stored in the `path` pickle file 
        """
        try:
            with open(path, 'rb') as f:
                data = pickle.load(f)
                self.update( data )
                
            print( len(data), 'metadata loaded from `%s`' % path )
        
        except FileNotFoundError:
            print( '`%s` not found.' % path  )  
    
    
    def save_pickle(path):
        """ if path dont exist: save
            else: ask confirm overwrite
        """
        pass    
    # to do: separate query and get
    # import(pickle) // allow multiple file... still 
    # save(pickle)
    # check_for_missing -> list of doi  with count 
    # ask( doi | list of doi )  - perform the query
    # getlabel(doi) 
    
    def get(self, doi):
        """ Get the metadata for the give doi
            look first in the cache
            if not present, perform the query
        """
        if doi in self:
            metadata = self[doi]
        else:
            metadata = self._query(doi)
        
        return MetaData( metadata )
        
        
    def _query(self, doi):
        """ Perform the query on Crossref if missing
            update the cache and save to the pickle file
        """
        print( 'retrieving metadata for {} from Crossref...'.format(doi), end='\r')
        
        url = 'https://api.crossref.org/works/'
        params = { 'mailto':self.mailadress }
        parsed_url = url + urllib.parse.quote_plus( doi )
        
        response = requests.get(parsed_url, params=params)
        
        if not response.ok:
            print('`%s` not found. Empty metadata created. ' % doi, end='\n')
            #raise NameError('query error: %s' % response.url )
            metadata = {'DOI': doi}
        else:
            print( 'metadata for {} retrieved from Crossref in {:3f} s.'.format(doi, response.elapsed.total_seconds()), end='\n' )
            response = response.json()
            metadata = response['message']
            
        self[doi] = metadata
        
        # save to file, create if not exist
        os.makedirs(os.path.dirname(self.cachelocation), exist_ok=True)
        with open(self.cachelocation, 'wb') as f:
            pickle.dump(self, f)
    
        return self[doi]
            
    
    def reset(self):
        """ Empty the cache and delete the cache file
        """
        cachesize = os.path.getsize(self.cachelocation) / 1024**2
        message = 'Delete `{}` {:.2f} Mo, \n Are you sure? [type yes] '
        confirm = input( message.format(self.cachelocation, cachesize ) )
        
        if confirm == 'yes':
            self.clear()
            os.remove(self.cachelocation)
            print('file removed')
        else:
            print('canceled')

    
    def _grow_one_gen(self, graph):
        """ Expand the given graph one generation
            by including all the papers cited by the last genreration
        """
        lastgen = graph.last_gen()
        lastgennodes = [ doi for doi, node in graph.items() if node['gen']==lastgen ]
        
        for i, doi in enumerate( lastgennodes ):
            print('{:3d}/{}: '.format( i, len(lastgennodes), doi ), end='')
            metadata = self.get( doi )
            doi_list = metadata.refs_doi()
            
            graph[doi]['refs'] = doi_list
            
            for ref_doi in doi_list:
                if ref_doi not in graph:
                    graph[ref_doi] = {'gen':lastgen+1, 'citedBy':[doi] }
                else:
                    graph[ref_doi]['citedBy'].append( doi )
                
        print('- done -' + ' '*12 )
        print( '{} nodes in the graph. The last generation number is {}.'.format(len(graph), graph.last_gen()) )


    def build_a_refgraph( self, doi, gen=2 ):
        """ Build a reference graph sarting from the `doi`
            for `gen` generations
        """
        gr = ReferenceGraph( doi )
        for k in range( gen ):
            self._grow_one_gen( gr )
        
        return gr
        
        
        
class MetaData(dict):
    """ Class representing the metadata information
    """
    
    def __init__(self, metadata):
        self.update( metadata )
        
        
    def refs_doi(self):
        """ List of doi of the references
        """
        references = self.get('reference', [])
        referencesWithDoi = { ref['DOI'] for ref in references if 'DOI' in ref }
        
        return list( referencesWithDoi )
    
    # not used?
    def label(self):
        """ Label for the article as AuthorYEAR
            return part of the hash is no metadata is found
        """        
        try:
            year = self['issued']['date-parts'][0][0]
            familyname = [ auth['family'] for auth in self['author'] if auth['sequence']=='first'][0]

            label = familyname + str(year)
        except KeyError:
            label = str( abs(hash( self['DOI'] )) )[:5]
            
        return label
    
    
    def printinfo(self):
        """ print nicely formated metadata
        """
        metadata = self
        try:
            title = metadata['title'][0]
            title = (title[:75].strip() + '...') if len(title) > 75 else title

            year = metadata['issued']['date-parts'][0][0]

            first_author = ' '.join([ (auth['given'], auth['family'])
                                     for auth in metadata['author']
                                     if auth['sequence']=='first'][0] )

            journal = metadata.get('container-title', '')[0]

            info = '({year}) {title}\n'.format(year=year, title=title)
            info += '   ' + first_author + ' et al.'
            info += ' - ' + journal
            info += '\n   ' + metadata['URL']

        except KeyError:
            info = '[%s] no meta data :(' % metadata['DOI']

        print( info )
    
    
    
# --- reference graph ---

class ReferenceGraph(dict):
    """ reference graph Object
        starting from one article 
        
        Each node include:
            - its generation number
            - the citedBy list
            
        The growth operation is performed by the Store
    """
    
    def __init__(self, doi):
        """ Init the graph with the DOI of root article
        """
        self[doi] = { 'gen':0, 'citedBy':[] }

        
    def last_gen(self):
        """ Get the number of the last generation
        """
        return max( node['gen'] for node in self.values() )
    
    
    def most_cited(self):
        """ Get the most cited articles in the graph
        """
        citedBy_count = [(doi,len(node['citedBy'])) for doi, node in self.items()]
        
        return sorted( citedBy_count, key=lambda x:x[1], reverse=True )
    
    
    def upward_graph(self, N=4):
        """ Build a new graph starting from the N-top cited article
        
            return the list of nodes, and the list of edges
        """
        nodes_to_check = [ node for node, count in self.most_cited()[:N] ]
        nodes_to_draw, links_to_draw = [], []
        while nodes_to_check:
            doi = nodes_to_check.pop()
            nodes_to_draw.append(doi)

            for citing in self[doi]['citedBy']:

                links_to_draw.append( (doi, citing) )
                
                if citing not in nodes_to_draw and citing not in nodes_to_check:
                    nodes_to_check.append( citing )

        return nodes_to_draw, links_to_draw
    

# --- Graphviz ---

# pip install graphviz
# https://graphviz.readthedocs.io/en/stable/
# https://graphviz.gitlab.io/_pages/doc/info/attrs.html
# color name: https://graphviz.gitlab.io/_pages/doc/info/colors.html

from graphviz import Digraph

def built_graphviz( nodes, links, getlabel, getcolor, secondary_links=[] ):
    """ Use Graphviz to draw the graph
        return a graphviz object

        - nodes is a list of nodes
        - links is a list of links (source, target)
        - getlabel = f(node) is a function wich return a label for a node
        - getcolor = f(node) is similar, return a color
        - secondary_links is a list of link which will have lower weight
    """
    def parsedoi( doi ): return doi.replace(':', '') # problem with graphviz?

    colorGen = ['red', 'gold1', 'cyan3', 'darkorchid2', 'chartreuse2']
    # see https://graphviz.gitlab.io/_pages/doc/info/colors.html

    DG = Digraph(comment='hello', format='svg', engine='dot',
                 graph_attr={'size':'8', 'nodesep':'.16', 'rankdir':'LR' })

    for doi in nodes:
        DG.node(parsedoi(doi), color=getcolor(doi), style='filled', label=getlabel(doi))

    for source, target in links:
        DG.edge(parsedoi(source), parsedoi(target), weight="5", style="solid", penwidth="1.4")  

    # http://www.graphviz.org/doc/info/attrs.html#d:weight
    for source, target in secondary_links:
        DG.edge(parsedoi(source), parsedoi(target), weight="1", color='lightcyan3', penwidth=".7")
        #, arrowtail='dot') 
        
    return DG



import networkx as nx

def filter_double_links( links ):
    """ 'knowledge' filtering
        remove link if a longer path exist
    """

    G = nx.DiGraph()
    for source, target in links:
        G.add_edge(source, target) 

    remaining_links = []
    for source, target in links:

        for path in nx.all_simple_paths( G, source, target ):
            if len(path)>2:
                break
        else:
            remaining_links.append( (source, target)  )

    return remaining_links