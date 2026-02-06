import re
from urllib.parse import urlparse, urljoin, urldefrag, urlsplit, urlunsplit, parse_qsl, parse_qs, urlencode
from collections import defaultdict
from bs4 import BeautifulSoup


STOP_WORDS = ['a', 'about', 'above', 'after', 'again', 'against', 'all', 'am', 'an', 
              'and', 'any', 'are', "aren't", 'as', 'at', 'be', 'because', 'been', 'before', 
              'being', 'below', 'between', 'both', 'but', 'by', "can't", 'cannot', 'could', 
              "couldn't", 'did', "didn't", 'do', 'does', "doesn't", 'doing', "don't", 'down', 
              'during', 'each', 'few', 'for', 'from', 'further', 'had', "hadn't", 'has', 
              "hasn't", 'have', "haven't", 'having', 'he', "he'd", "he'll", "he's", 'her', 
              'here', "here's", 'hers', 'herself', 'him', 'himself', 'his', 'how', "how's", 
              'i', "i'd", "i'll", "i'm", "i've", 'if', 'in', 'into', 'is', "isn't", 'it', 
              "it's", 'its', 'itself', "let's", 'me', 'more', 'most', "mustn't", 'my', 'myself', 
              'no', 'nor', 'not', 'of', 'off', 'on', 'once', 'only', 'or', 'other', 'ought', 
              'our', 'ours', 'ourselves', 'out', 'over', 'own', 'same', "shan't", 'she', 
              "she'd", "she'll", "she's", 'should', "shouldn't", 'so', 'some', 'such', 
              'than', 'that', "that's", 'the', 'their', 'theirs', 'them', 'themselves', 
              'then', 'there', "there's", 'these', 'they', "they'd", "they'll", "they're", 
              "they've", 'this', 'those', 'through', 'to', 'too', 'under', 'until', 'up', 
              'very', 'was', "wasn't", 'we', "we'd", "we'll", "we're", "we've", 'were', 
              "weren't", 'what', "what's", 'when', "when's", 'where', "where's", 'which', 
              'while', 'who', "who's", 'whom', 'why', "why's", 'with', "won't", 'would', 
              "wouldn't", 'you', "you'd", "you'll", "you're", "you've", 'your', 'yours', 
              'yourself', 'yourselves']


MAX_PARAMS = 6
MAX_QUERY_LEN = 120

ALLOWED_DOMAINS = (
    "ics.uci.edu",
    "cs.uci.edu",
    "informatics.uci.edu",
    "stat.uci.edu"
)

TRAP_QUERY_KEYS = {
    "share", "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "replytocom", "redirect_to",
    "do", "tab_files", "tab_details", "image", "ns", "idx"
}

TRAP_PATH_SUBSTRINGS = (
    "/wp-login", "/wp-admin", "logout", "lostpassword",
    "/mailman/admin", "/mailman/private",
)

PATH_QUERY_VARIANTS = defaultdict(int)
MAX_VARIANTS_PER_PATH = 50

def scraper(url, resp):
    out = []
    for link in extract_next_links(url, resp):
        n = normalize_url(link)
        if is_valid(n):
            out.append(n)
    return out

def has_trap_query(parsed) -> bool:
    # Checks if URL has a query that will trap the crawler
    for k, _ in parse_qsl(parsed.query, keep_blank_values=True):
        if k.lower() in TRAP_QUERY_KEYS:
            return True
    return False

def has_trap_path(path: str) -> bool:
    # Checks if URL has a path that will trap the crawler
    p = path.lower()
    return any(t in p for t in TRAP_PATH_SUBSTRINGS)

def too_many_variants(url: str) -> bool:
    s = urlsplit(url)
    key = (s.netloc.lower(), s.path.lower())
    if s.query:
        PATH_QUERY_VARIANTS[key] += 1
        return PATH_QUERY_VARIANTS[key] > MAX_VARIANTS_PER_PATH
    return False

def _to_text(content : str) -> str:
    # Converts webpage content into text
    if content is None:
        return ""
    if isinstance(content, bytes):
        return content.decode("utf-8", errors = "ignore")
    return str(content)

def host_allowed(host : str) -> bool:
    # Checks if hostname is allowed
    return any(host == d or host.endswith("." + d) for d in ALLOWED_DOMAINS)

def normalize_url(url: str) -> str:
    # Simplifies URL into a base form to reduce duplicate URLs
    s = urlsplit(url)
    scheme = s.scheme.lower()
    netloc = s.netloc.lower()

    path = s.path
    if path.endswith("/") and path != "/":
        path = path[:-1]

    # simplify query section of URL
    params = [(k, v) for (k, v) in parse_qsl(s.query, keep_blank_values=False)]
    params.sort()
    if len(params) > MAX_PARAMS:
        params = params[:MAX_PARAMS]
    query = urlencode(params, doseq=True)
    if len(query) > MAX_QUERY_LEN:
        query = query[:MAX_QUERY_LEN]

    # remove fragment section from URL
    return urlunsplit((scheme, netloc, path, query, ""))

def _link_extractor(raw_html: str, base_url: str):
    # Tokenizes HTML content from a page
    html = _to_text(raw_html)
    soup = BeautifulSoup(html, "html.parser")
    found = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        href = href.strip()
        if not href or href.startswith(("mailto:", "javascript:", "tel:")):
            continue
        joined = urljoin(base_url, href)
        defragged, _ = urldefrag(joined)
        found.add(normalize_url(defragged))
    return list(found)


def extract_next_links(url, resp):
    # Implementation required.
    # url: the URL that was used to get the page
    # resp.url: the actual url of the page
    # resp.status: the status code returned by the server. 200 is OK, you got the page. Other numbers mean that there was some kind of problem.
    # resp.error: when status is not 200, you can check the error here, if needed.
    # resp.raw_response: this is where the page actually is. More specifically, the raw_response has two parts:
    #         resp.raw_response.url: the url, again
    #         resp.raw_response.content: the content of the page!
    # Return a list with the hyperlinks (as strings) scrapped from resp.raw_response.content
    
    if resp.status != 200 or resp.raw_response is None or resp.raw_response.content is None:
        return []

    content = resp.raw_response.content
    base = resp.url
    return _link_extractor(content, base)

def is_valid(url):
    # Decide whether to crawl this url or not. 
    # If you decide to crawl it, return True; otherwise return False.
    # There are already some conditions that return False.
    try:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return False

        host = parsed.hostname
        if host is None or not host_allowed(host):
            return False

        if has_trap_path(parsed.path):
            return False

        if has_trap_query(parsed):
            return False

        if too_many_variants(url):
            return False

        return not re.match(
            r".*\.(css|js|bmp|gif|jpe?g|ico"
            r"|png|tiff?|mid|mp2|mp3|mp4"
            r"|wav|avi|mov|mpeg|ram|m4v|mkv|ogg|ogv|pdf"
            r"|ps|eps|tex|ppt|pptx|doc|docx|xls|xlsx|names"
            r"|data|dat|exe|bz2|tar|msi|bin|7z|psd|dmg|iso"
            r"|epub|dll|cnf|tgz|sha1"
            r"|thmx|mso|arff|rtf|jar|csv"
            r"|rm|smil|wmv|swf|wma|zip|rar|gz)$",
            parsed.path.lower()
        )
    except TypeError:
        return False
