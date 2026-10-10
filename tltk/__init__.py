"""Minimal TLTK package loader for Piper's Thai phonemizer.

Piper only needs ``tltk.nlp.th2ipa``.  TLTK's stock package initializer also
loads its optional corpus module, which imports Gensim.  Gensim has no Python
3.14-compatible build yet, although the phonemizer itself does not use it.
This namespace shim exposes the installed ``tltk.nlp`` module without loading
the unrelated corpus features.
"""

from pkgutil import extend_path

__path__ = extend_path(__path__, __name__)
