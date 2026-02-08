import re
import atexit
import threading
from urllib.parse import (
    urlparse, urljoin, urldefrag, urlsplit, urlunsplit,
    parse_qsl, urlencode
)
from collections import defaultdict, Counter
from bs4 import BeautifulSoup


STOP_WORDS = [
    'a','about','above','after','again','against','all','am','an','and','any','are',
    'as','at','be','because','been','before','being','below','between','both','but',
    'by','could','did','do','does','doing','down','during','each','few','for','from',
    'further','had','has','have','having','he','her','here','hers','herself','him',
    'himself','his','how','i','if','in','into','is','it','its','itself','me','more',
    'most','my','myself','no','nor','not','of','off','on','once','only','or','other',
    'our','ours','ourselves','out','over','own','same','she','should','so','some',
    'such','than','that','the','their','theirs','them','themselves','then','there',
    'these','they','this','those','through','to','too','under','until','up','very',
    'was','we','were','what','when','where','which','while','who','whom','why','with',
    'you','your','yours','yourself','yourselves'
]

# words that are common on *your domains* but useless for "top words"
DOMAIN_STOP_WORDS = {
    "ics", "uci", "edu", "wiki", "php", "doku", "https", "http",
    "login", "password", "account", "email", "access", "support",
    "please", "ssh", "key", "credentials", "authentication", "restricted",
    "obtaining", "privileges", "logged", "remember", "cookies", "affiliates",
    "insufficient", "enabled", "enter", "currently", "make", "sure",
    "helpdesk", "hardware", "software", "services", "group", "log",
    "page", "pages", "section", "file", "files", "user", "users"
}

# not strictly needed if you use the manual tokenizer, but fine to keep
WORD_RE = re.compile(r"[a-zA-Z0-9]+(?:['-][a-zA-Z0-9]+)?")

ALLOWED_DOMAINS = (
    "ics.uci.edu",
    "cs.uci.edu",
    "informatics.uci.edu",
    "stat.uci.edu"
)

# query keys that indicate infinite calendars, search pages, tracking params, etc.
TRAP_QUERY_KEYS = {
    "outlook-ical", "ical", "tribe-bar-date", "eventdisplay",
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "share", "replytocom", "redirect_to", "ajax", "format", "feed",
    "do", "idx", "rev", "tab", "ns", "search", "q",
    "s", "id", "page", "offset", "limit", "start",
    "sort", "order", "filter", "view"
}

# path substrings that often represent trap-like navigation
TRAP_PATH_SUBSTRINGS = (
    "/calendar", "/events/", "/event/", "/feed", "/rss", "/xml", "/json",
    "/wp-admin", "/wp-login", "/tag/", "/category/", "/author/",
    "/print/", "/pdf/", "/export/", "/download/",
    "/search", "/query", "/results", "/action/", "/special/",
    "/recent", "/revisions", "/history",
)

MIN_WORDS = 50
MAX_PARAMS = 6
MAX_QUERY_LEN = 120
MAX_VARIANTS_PER_PATH = 50