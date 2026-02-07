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
    "replytocom", "redirect_to", "do", "tab_files", "tab_details", "image", "ns", 
    "idx", "outlook-ical", "ical", "calendar", "date", "year", "month", "day", "week",
    "start", "end", "from", "to", "time", "timestamp", "page", "p", "offset", "limit",
    "size", "count", "sort", "order", "filter", "search", "q", "ajax", "action", "format",
    "view", "mode", "feed", "rss", "xml", "json", "atom"
}

TRAP_PATH_SUBSTRINGS = (
    "/wp-login", "/wp-admin", "/logout", "/lostpassword",
    "/mailman/admin", "/mailman/private", "/calendar", "/events/",
    "/event/", "/archive/", "/feed", "/rss", "/atom", "/xml", "/json",
    "/search", "/tag/", "/category/", "/author/", "/print", "/pdf",
    "/download", "/attachment"
)

PATH_QUERY_SEEN = defaultdict(set)
MAX_VARIANTS_PER_PATH = 50

MIN_WORDS = 50