#!/usr/bin/env python3
import setup_test
import libxml2
import sys

libxml2.debugMemory(True)

expect = """--> Invalid expression
--> Invalid expression
--> Invalid expression
--> Invalid expression
--> Invalid expression
--> Invalid expression
--> Invalid expression
--> Invalid expression
--> Invalid expression
--> Invalid expression
"""
err = ""


def callback(ctx, str):
    global err

    err = err + "%s %s" % (ctx, str)


libxml2.registerErrorHandler(callback, "-->")

doc = libxml2.parseDoc("<fish/>")
ctxt = doc.xpathNewContext()
ctxt.setContextNode(doc)
badexprs = (
    ":false()",
    "bad:()",
    "bad(:)",
    ":bad(:)",
    "bad:(:)",
    "bad:bad(:)",
    "a:/b",
    "/c:/d",
    "//e:/f",
    "g://h",
)
for expr in badexprs:
    try:
        ctxt.xpathEval(expr)
    except libxml2.xpathError:
        pass
    else:
        print("Unexpectedly legal expression:", expr)
ctxt.xpathFreeContext()
doc.freeDoc()

if err != expect:
    print("error")
    print("received %s" % (err))
    print("expected %s" % (expect))
    sys.exit(1)

libxml2.cleanupParser()
leakedbytes = libxml2.debugMemory(True)
if leakedbytes == 0:
    print("OK")
else:
    print("Memory leak", leakedbytes, "bytes")
