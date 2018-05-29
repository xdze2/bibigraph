import bibtexparser as bib
import re


def appendToDico( dico, key, value ):
    ''' Simple tool to populate a dict of list
    '''
    if key in dico:
        dico[key].append( value )
    else:
        dico[key] = [value]

        
class Bibliography(object):
    ''' It's the library, including all the articles
    '''
    
    def __init__(self):    
        self.articles = []
        self.keyToIndex = {}
        self.authors = {}
    
    def load(self, datafile):
        """ Read and parse the file at the given path,
            add the entries to the bibliography
        """
        with open(datafile) as bibtex_file:
            bibdata = bib.load(bibtex_file)

        articlelist = [ Article( entry ) for entry in bibdata.entries ]
        self.articles.extend( articlelist )
        self.update()
        print( len(bibdata.entries), 'articles added' )

        
    def countByYears(self):
        ''' Return the list of tuples [(year, count),... ]
        '''
        count_by_years = {}
        for article in self.articles:
            year = article.year
            count_by_years[year] = count_by_years.get( year, 0 ) + 1

        return sorted( count_by_years.items(), key=lambda x:x[0]  )


    def update( self ):
        ''' update the indexes
        '''
        self.keyToIndex = {}
        for k, entry in enumerate( self.articles ):
            self.keyToIndex[entry.key] = k
        
        self.authors = {}
        for entry in self.articles :
            for author in entry.authors:
                appendToDico( self.authors, author, entry.key  ) 

                
    def getTopAuthors(self, n=3, m=10):
        authors = [ (a, p) for a, p in self.authors.items() if len(p)>n ]
        return sorted( authors, key=lambda x:len(x[1]), reverse=True )[:m]
       
    def getTopCited(self, m=4):
        key_citation = [ (a.key, a.nbrCitation) for a in self.articles ]
        return sorted( key_citation, key=lambda x:x[1], reverse=True )[:m]
        
    def getArticleFromKey(self, key ):
        return self.articles[ self.keyToIndex[key] ]
        
    
class Article(object):
    
    def __init__(self, entry):
        """ Create the Article instance
            from the dictionary of raw data
        """
        self.raw = entry
        
        self.year = int( entry['year'] )
        
        authorlist = entry['author'].split(' and ')
        self.authors = [a.strip() for a in authorlist]
        
        self.title = entry['title']
        self.type = entry['document_type']
        self.journal = entry['journal']
        self.key = entry['ID']
        self.nbrCitation = int( re.findall('cited By ([0-9]+)', entry['note'])[0] )
       
        self.affiliation = entry['affiliation'].split(';') if 'affiliation' in entry else []

    def __str__(self):
        text = ''
        text += self.title + ' (%i)'%self.year + '\n'
        text += ', '.join(self.authors)
        
        return text
    
    def __repr__(self):
        text = ''
        text += self.title[:30] + '... (%i) '%self.year 
        text += self.journal
        return text