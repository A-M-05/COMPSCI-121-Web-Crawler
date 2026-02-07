from imports import *
from helpers import *

def scraper(url, resp):
    """
    Process a fetched web page: reject invalid or low-information pages, extract and
    normalize outgoing links, and return only those URLs that are valid for crawling.
    """

    # Reject non-200 / empty URLS
    if resp.status != 200 or resp.raw_response is None or resp.raw_response.content is None:
        return []

    html = to_text(resp.raw_response.content)
    text = extract_visible_text(html)
    tokens = tokenize_text(text)

    if len(tokens) < MIN_WORDS:
        return []

    out = []
    for link in link_extractor(html, resp.url):
        n = normalize_url(link)
        if is_valid(n):
            out.append(n)
    return out

def extract_next_links(url, resp):
    """
    Extract all outgoing hyperlinks from a successfully fetched web page response
    and return them as a list of absolute URLs.
    """
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
    return link_extractor(content, base)

def is_valid(url):
    """
    Determine whether a URL is allowed to be crawled based on scheme, domain,
    path patterns, query parameters, trap detection, and file type restrictions.
    """
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
