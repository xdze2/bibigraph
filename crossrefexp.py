import requests
import urllib.parse
import pickle
import time
import os
import re

class MetaDataStore(dict):
    """ Store for the metadata
        and interface to the Crossref API
    """

    def __init__(self, cachelocation='data/cachefile.pickle'):
        """ Load the cached metadata from the `cachelocation` filename
        """
        self.cachelocation = cachelocation
        self.mailadress = 'xdze2.me@gmail.com'

        if os.path.isfile(self.cachelocation):
            self.import_pickle(self.cachelocation)
        else:
            print('default pickle location set to %s' % self.cachelocation)

    def import_pickle(self, path):
        """ Import the metadata stored in the given `path` pickle file.
        """
        try:
            with open(path, 'rb') as f:
                data = pickle.load(f)
                self.update(data)

            print(len(data), 'metadata loaded from `%s`' % path)

        except FileNotFoundError:
            print('`%s` not found.' % path)

    def save(self, path=None):
        """ Save metadata to a pickle file
            if no path specified, save to the default path
        """
        if path is None:
            path = self.cachelocation

        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            pickle.dump(self, f)

        print( '%s saved.'%path )


    def get(self, doi_list):
        """ Return the metadata for the given doi list (or str doi)
            look first in the cache
            if not present, return an empty MetaData object

            note: store[key] return a dict
        """
        if isinstance(doi_list, str):
            return self._get_one(doi_list)

        metadata_list = []
        for doi in doi_list:
            metadata_list.append( self._get_one(doi) )

        return metadata_list

    def _get_one(self, doi):
        """ Return the metadata for the given doi list (or str doi)
            look first in the cache
            if not present, return an empty MetaData object

            note: store[key] return a dict
        """
        doi = doi.lower()
        if doi in self:
            return MetaData(self[doi])
        else:
            return MetaData({'DOI': doi})

    def query(self, doi_list):
        """ Get the metadata for the given list of doi
            look first in the cache
            if not present, perform the query
        """
        if not doi_list:
            return

        if isinstance(doi_list, str): doi_list = [doi_list]

        print('Requesing {} metadata:'.format(len(doi_list)))
        metadata = query_crossref(doi_list,
                                  email = self.mailadress)
        self.update( metadata )
        self.save()

    def _grow_one_gen(self, graph):
        """ Expand the given graph one generation
            by including all the papers cited by the last genreration
        """
        lastgen = graph.last_gen()
        lastgennodes = [doi for doi, node in graph.items()
                        if node['gen'] == lastgen]

        missing = [doi for doi in lastgennodes if doi not in self]
        self.query(missing)

        for i, doi in enumerate(lastgennodes):
            metadata = self.get(doi)
            references = metadata.get('reference', [])
            references_with_doi = {ref['DOI'].lower() for ref in references
                                   if 'DOI' in ref}

            graph[doi]['refs'] = references_with_doi

            for ref_doi in references_with_doi:
                if ref_doi not in graph:
                    graph[ref_doi] = {'gen': lastgen+1, 'citedBy': [doi]}
                else:
                    graph[ref_doi]['citedBy'].append(doi)

        print('growth achieved - {} nodes in the graph. The last generation number is {}.'
              .format(len(graph), graph.last_gen()))

    def build_a_refgraph(self, doi_list, gen=2):
        """ Build a reference graph starting from the given doi_list`
            and for `gen` generations.
        """
        gr = ReferenceGraph(doi_list)
        for k in range(gen):
            self._grow_one_gen(gr)

        return gr

    def get_refgraphviz(self, doi_list, gen=2, top=3, starting_from=None,
                        save=True, draw_secondary_links=True):
        """ Build the reference graph for `gen` generations, starting at the
            articles in `doi_list`. Then, keep only the upward graph generated
            from the `top`-cited references. Return a Graphviz object.

            Parameters
            ----------
            doi_list: list of doi string or one doi string
            gen: int, default 2
                number of generation
            top: int, default 3, -1 for all
                number of references to start from when generating the upward graph
            starting_from: list of doi
                then top is ignored
            save: bool, default True
                if True save the graph in a svg file
            draw_secondary_links: default True
                if False do not draw the secondary links
                (a link is considered secondary if a longer path exist)
        """
        print('assembling the graph...', end='\r')
        
        if isinstance(doi_list, str):
            doi_list = [doi_list]

        # Build the upward graph starting from the top-N cited articles
        gr = self.build_a_refgraph(doi_list, gen=gen)
        nodes, links = gr.upward_graph(top, doi_list=starting_from)

        # Query for the top-cited nodes of the last generation:
        missing = [doi for doi in nodes if doi not in self]
        self.query(missing)

        # 'Knowledge' filtering:
        print('filtering the edges...', end='\r')
        remaining_links = filter_double_links(links)
        no_weight_links = [link for link in links
                           if link not in remaining_links]
        no_secondary_tag = ''

        if not draw_secondary_links:
            no_weight_links = []
            no_secondary_tag = '_noSecondaryLink'

        # Draw:
        def getlabel(doi): return self.get(doi).label()

        color_list = ['red', 'gold1', 'cyan3', 'darkorchid2', 'chartreuse2']
        def getcolor(doi): return color_list[ gr[doi]['gen'] ]

        print('building the layout...', end='\r')
        graph_vizu = built_graphviz(nodes, remaining_links,
                                    getlabel, getcolor,
                                    gettooltip=self.get_info,
                                    secondary_links=no_weight_links)

        # Save the svg file:
        if save:
            subdir = 'graphs/'
            concatenate_keys = ''.join( getlabel(doi) for doi in doi_list )[:20]
            filename = '{}_gen{}_top{}{}'.format(concatenate_keys, gen, top, no_secondary_tag)
            fn = graph_vizu.render(filename=filename, cleanup=True, directory=subdir)
            print('%s  saved'%fn)

        return graph_vizu

    def get_info(self, doi):
        """ Return a nicely formated text giving the metadata for the `doi`.
            Used for the node's tooltip.
        """
        metadata = self.get(doi)
        try:
            title = ''.join( metadata['title'] )
            title = (title[:75].strip() + '...') if len(title) > 75 else title

            year = metadata['issued']['date-parts'][0][0]

            authors = ', '.join([' '.join((auth['given'], auth['family']))
                                for auth in metadata['author']])

            journal = metadata.get('container-title', '')[0]

            refcount = metadata['reference-count']
            refdoicount = len(metadata.refs_doi())

            iscitedby_count = metadata.get("is-referenced-by-count", '-na-')
            info = """\
            {title}
            ({year}) {journal}
            {authors}
            {refcount} references - {reflen} given and {refdoicount} with doi
            {iscitedby_count} times cited.
            """.format(year=year, title=title, authors=authors,
                       journal=journal, refcount=refcount,
                       refdoicount=refdoicount, reflen=len(metadata.get('reference', [])),
                       iscitedby_count=iscitedby_count)

            info = info.replace('  ', '')

        except KeyError:
            info = '[%s] no meta data :(' % metadata['DOI']

        return info


class MetaData(dict):
    """ Class representing the metadata information."""

    def __init__(self, metadata):
        self.update(metadata)

    def refs_doi(self):
        """ List of doi of the references.
        """
        references = self.get('reference', [])
        references_with_doi = {ref['DOI'] for ref in references
                               if 'DOI' in ref}

        return list(references_with_doi)

    def label(self):
        """ Label for the article as AuthorYEAR.
            Return part of the hash is no metadata is found.
        """
        try:
            year = self['issued']['date-parts'][0][0]
            familyname = [auth['family'] for auth in self['author']
                          if auth['sequence'] == 'first'][0]

            label = familyname + str(year)
        except KeyError:
            label = str( abs(hash( self['DOI'] )) )[:5]

        return label

    def printinfo(self):
        """ Print nicely formated metadata.
        """
        metadata = self
        try:
            title = metadata['title'][0]
            title = (title[:75].strip() + '...') if len(title) > 75 else title

            year = metadata['issued']['date-parts'][0][0]

            first_author = ' '.join([ (auth['given'], auth['family'])
                                    for auth in metadata['author']
                                    if auth['sequence'] == 'first'][0] )

            journal = metadata.get('container-title', [''])[0]

            info = '({year}) {title}\n'.format(year=year, title=title)
            info += '   ' + first_author + ' et al.'
            info += ' - ' + journal
            info += '\n   ' + metadata['URL']

        except KeyError:
            info = '[%s] no meta data :(' % metadata['DOI']

        print(info)


# --- reference graph ---

class ReferenceGraph(dict):
    """ Reference graph Object.

        Each node include:
            - its generation number
            - the citedBy list

        The growth operation is performed by the Store
    """

    def __init__(self, doi_list):
        """ Init the graph with the DOI of root article.
        """
        if isinstance(doi_list, str):
            doi_list = [doi_list]

        for doi in doi_list:
            doi = doi.lower()
            self[doi] = {'gen': 0, 'citedBy': []}


    def last_gen(self):
        """ Get the number of the last generation.
        """
        return max( node['gen'] for node in self.values() )


    def most_cited(self):
        """ Get the most cited articles in the graph.
        """
        citedBy_count = [(doi, len(node['citedBy'])) for doi, node in self.items()]

        return sorted( citedBy_count, key=lambda x:x[1], reverse=True )


    def upward_graph(self, N=4, doi_list=None):
        """ Build a new graph starting from the N-top cited article.
            Return the list of nodes, and the list of edges
        """
        if doi_list:
            nodes_to_check = doi_list
        else:
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


def built_graphviz(nodes, links, getlabel, getcolor,
                   gettooltip=lambda x:None, secondary_links=[] ):
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
        DG.node(parsedoi(doi), color=getcolor(doi), style='filled',
                label=getlabel(doi), tooltip=gettooltip(doi))

    for source, target in links:
        DG.edge(parsedoi(source), parsedoi(target), weight="5",
                style="solid", penwidth="1.4")

    # http://www.graphviz.org/doc/info/attrs.html#d:weight
    for source, target in secondary_links:
        DG.edge(parsedoi(source), parsedoi(target), weight="1",
                color='lightcyan3', penwidth=".7")
        # , arrowtail='dot')

    return DG



import networkx as nx

def filter_double_links( links ):
    """ 'knowledge' filtering
        remove link if a longer path exist
        `links` is a list of link [(source, target), ... ]
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



def query_crossref(doi_list, email = ''):
    """ Retrieve metadata from the Crossref API.
        Group the doi to reduce the number of queries.
    """
    max_query_size = 92
    
    # Formatting and filtering the doi_list
    doi_pattern = re.compile(r'^10.\d{4,9}\/[-._;()\/:A-Z0-9]+$', re.IGNORECASE)

    len_before_filtering = len(doi_list)
    doi_list = [ doi for doi in doi_list if re.match(doi_pattern, doi) ]
    if len(doi_list) != len_before_filtering:
        print('warning: some doi not well formatted, ignored')

    doi_list = list(set( doi_list ))  # filter doublon
    doi_list = [doi.lower() for doi in doi_list]
    
    sliced_doi_list = [doi_list[i:i + max_query_size]
                       for i in range(0, len(doi_list), max_query_size)]
    
    returned_metadata = {}
    for chunck_doi_list in sliced_doi_list:

        concatenated_doi_list = ','.join( 'doi:%s' % doi for doi in chunck_doi_list )
        url = 'http://api.crossref.org/works'
        params = {'mailto': email,
                  'filter': concatenated_doi_list,
                  'rows': len(chunck_doi_list)}

        response = requests.get(url, params=params)

        print('Query performed in {:3f} s. ({} doi)'
              .format(response.elapsed.total_seconds(), len(chunck_doi_list)), end='\n')

        if not response.ok:
            print('query error: %s' % response.content)
        else:
            response = response.json()
            len_answer = response['message']['total-results']
            items = response['message']['items']

            returned_metadata.update( {meta['DOI'].lower():meta for meta in items} )

    print( '{} metadata returned for {} asked'.format(len(returned_metadata), len(doi_list)) )

    missing = set(doi_list) - returned_metadata.keys()
    if missing:
        print( 'missing doi (%i):' % len(missing), ' '.join(missing) )
        for doi in missing:
            returned_metadata[doi] = {'DOI':doi, 'status':'missing'}

    return returned_metadata