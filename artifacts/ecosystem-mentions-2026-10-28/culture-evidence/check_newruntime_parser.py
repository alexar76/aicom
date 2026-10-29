from html.parser import HTMLParser
class Extract(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts=[]; self.links=[]; self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'):self.skip+=1
        if tag=='a':
            d=dict(attrs)
            if d.get('href'):self.links.append(d['href'])
    def handle_endtag(self,tag):
        if tag in ('script','style'):self.skip=max(0,self.skip-1)
    def handle_data(self,s):
        if not self.skip and s.strip():self.parts.append(s.strip())

