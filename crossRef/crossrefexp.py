import requests
import urllib.parse
import pickle
import time
import os

# useless
class MetaDataStore(dict):
    """ Store and get the metadata from Crossref
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

        
    def get(self, doi):
        if doi in self:
            return self['doi']
        else:
            return self._query(doi)
        
        
    def _query(self, doi):
        """ Perform the query on Crossref if missing
            update the cache and save to the pickle file
        """
        
        url = 'https://api.crossref.org/works/'
        params = { 'mailto':self.mailadress }
        parsed_url = url + urllib.parse.quote_plus( doi )
        
        response = requests.get(parsed_url, params=params)
        
        if not response.ok:
            print('`%s` not found. Empty metadata created. ' % doi)
            #raise NameError('query error: %s' % response.url )
            metadata = {'DOI': doi}
        else:
            print( 'metadata retrieved from Crossref in %.3f s.' % response.elapsed.total_seconds() )
            response = response.json()
            metadata = response['message']
            
        self[doi] = metadata
        
        # save to file, create if not exist
        os.makedirs(os.path.dirname(self.cachelocation), exist_ok=True)
        with open(self.cachelocation, 'wb') as f:
            pickle.dump(self, f)

            
        return MetaData( metadata )
        
        
    def __getitem__(self, key):
        """ Wrap the returned value in a MetaData object
        """
        value = dict.__getitem__(self, key)
        return  MetaData( value )
    
    
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

            
def initMetadataStore(cachelocation = 'data/cachefile.pickle'):
    
    mailadress = 'xdze2.me@gmail.com'
    cache = {}

    try:
        with open(cachelocation, 'rb') as f:
            cache.update( pickle.load(f) )
        print( len(cache), 'metadata loaded from `%s`' % cachelocation )
    except FileNotFoundError:
        print( '`%s` not found. A new file will be created.' % cachelocation  )
    
    def get_metadata(doi):
        """ Perform the query on Crossref if not in cache
            update the cache and save to the pickle file
            return a MetaData object
        """
        if doi in cache:
            return cache[doi]
        else:
            url = 'https://api.crossref.org/works/'
            params = { 'mailto':mailadress }
            parsed_url = url + urllib.parse.quote_plus( doi )

            response = requests.get(parsed_url, params=params)

            if not response.ok:
                print('`%s` not found. Empty metadata created. ' % doi)
                metadata = {'DOI': doi}
            else:
                print( 'metadata retrieved from Crossref in %.3f s.' % response.elapsed.total_seconds() )
                response = response.json()
                metadata = response['message']

            cache[doi] = MetaData( metadata )

            # save to file, create if not exist
            os.makedirs(os.path.dirname(cachelocation), exist_ok=True)
            with open(cachelocation, 'wb') as f:
                pickle.dump(cache, f)

            return cache[doi]
        
    return get_metadata
        

class MetaData(dict):
    """ Class based on a dict representing the metadata
    """
    
    def __init__(self, metadata):
        self.update( metadata )
        
        
    def refs_doi(self):
        """ List of doi of the references
        """
        references = self.get('reference', [])
        referencesWithDoi = { ref['DOI'] for ref in references if 'DOI' in ref }
        
        return list( referencesWithDoi )
    
    
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
    
    
    def print_node_info(self):
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
    """ Object to explore the reference graph
        starting from one article 
    """
    
    def __init__(self, doi, cachelocation = 'data/cachefile.pickle'):
        """ Init the graph with the DOI of root article
        """
        self[doi] = { 'gen':0, 'citedBy':[] }

        # cache:
        self.cachelocation = cachelocation
        self.mailadress = 'xdze2.me@gmail.com'
        self.cache = {}
    
        try:
            with open(self.cachelocation, 'rb') as f:
                self.cache.update( pickle.load(f) )
            print( len(self.cache), 'metadata loaded from `%s`' % self.cachelocation )
        except FileNotFoundError:
            print( '`%s` not found. A new file will be created.' % self.cachelocation  )
            
    
    def get_metadata(self, doi):
        """ Perform the query on Crossref if not in cache
            update the cache and save to the pickle file
            return a MetaData object
        """
        if doi in self.cache:
            return self.cache[doi]
        else:
            url = 'https://api.crossref.org/works/'
            params = { 'mailto':self.mailadress }
            parsed_url = url + urllib.parse.quote_plus( doi )

            response = requests.get(parsed_url, params=params)

            if not response.ok:
                print('`%s` not found. Empty metadata created. ' % doi)
                metadata = {'DOI': doi}
            else:
                print( 'metadata retrieved from Crossref in %.3f s.' % response.elapsed.total_seconds() )
                response = response.json()
                metadata = response['message']

            self.cache[doi] = MetaData( metadata )

            # save to file, create if not exist
            os.makedirs(os.path.dirname(self.cachelocation), exist_ok=True)
            with open(self.cachelocation, 'wb') as f:
                pickle.dump(self.cache, f)

            return self.cache[doi]
    
    
    def grow( self, N, get_metadata ):
        """ Expand the graph N generations
            by including all the papers cited by the last genreration
        """
        for k in range(N):
            self._grow_one_gen(get_metadata)
        
    
    def _grow_one_gen(self, get_metadata):
        """ Expand the graph one generation
            by including all the papers cited by the last genreration
        """
        lastgen = self.last_gen()
        lastgennodes = [ doi for doi, node in self.items() if node['gen']==lastgen ]
        
        for i, doi in enumerate( lastgennodes ):
            print('{}/{} fetch %s'.format( i, len(lastgennodes), doi ), end='\r')
            time.sleep(.7) # not here...
            metadata = get_metadata( doi )
            doi_list = metadata.refs_doi()
            
            self[doi]['refs'] = doi_list
            
            for ref_doi in doi_list:
                if ref_doi not in self:
                    self[ref_doi] = {'gen':lastgen+1, 'citedBy':[doi] }
                else:
                    self[ref_doi]['citedBy'].append( doi )
                
        print('- done -' + ' '*10 )
        self.len = len( self )
                   
            
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

def built_graphviz( nodes, links, getlabel, getcolor ):
    """ Use Graphviz to draw the graph
        return a graphviz object

        - nodes is a list of nodes
        - links is a list of links (source, target)
        - getlabel = f(node) is a function wich return a label for a node
        - getcolor = f(node) is similar, return a color
    """
    def parsedoi( doi ): return doi.replace(':', '') # problem with graphviz?

    colorGen = ['red', 'gold1', 'cyan3', 'darkorchid2', 'chartreuse2']
    # see https://graphviz.gitlab.io/_pages/doc/info/colors.html

    DG = Digraph(comment='hello', format='svg', engine='dot',
                 graph_attr={'size':'10' })#})'root':doi} )
    DG.graph_attr['rankdir'] = 'LR'

    for doi in nodes:
        DG.node(parsedoi(doi), color=getcolor(doi), style='filled', label=getlabel(doi))

    for source, target in links:
        DG.edge(parsedoi(source), parsedoi(target))  

    return DG