#!/usr/bin/env python3
import sys
import setup_test
import libxml2

# Memory debug specific
libxml2.debugMemory(1)

#
# Testing XML document serialization
#
doc = libxml2.readDoc(
    """<?xml version="1.0" encoding="iso-8859-1"?>
<!DOCTYPE test [
<!ELEMENT test (#PCDATA) >
<!ATTLIST test xmlns:abc CDATA #FIXED "http://abc.org" >
<!ATTLIST test abc:attr CDATA #FIXED "def" >
]>
<test />
""",
    None,
    None,
    libxml2.XML_PARSE_DTDATTR,
)
elem = doc.getRootElement()
attr = elem.hasNsProp("attr", "http://abc.org")
print(attr.serialize())
if attr == None:
    print("Failed to find defaulted attribute abc:attr")
    sys.exit(1)

doc.freeDoc()

# Memory debug specific
libxml2.cleanupParser()
if libxml2.debugMemory(1) == 0:
    print("OK")
else:
    print("Memory leak %d bytes" % (libxml2.debugMemory(1)))
