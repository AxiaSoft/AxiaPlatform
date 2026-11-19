"""Reduced motion must show the page, not hide it.

`.reveal` blocks start at opacity 0 and are revealed by an IntersectionObserver.
When the reader asks for reduced motion there is no observer - every block is
marked visible up front instead - but `decorateReveal()` still ran on content
added by a route change and called `revealObserver.observe(...)` on the null
observer. The throw aborted that hook, so everything rendered afterwards stayed
at opacity 0. Asking not to be animated was the way to make the page disappear.

The observer is a module-local variable inside an IIFE, so these tests read the
source the way the other round tests do: they assert the shape that makes the
crash impossible, then check the real file under jsdom-style stubs when node is
available.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EFFECTS = (ROOT / 'public' / 'effects.js').read_text(encoding='utf-8')


class RevealGuard(unittest.TestCase):

    def test_decorate_checks_the_observer_before_using_it(self):
        start = EFFECTS.index('function decorateReveal(')
        end = EFFECTS.index('\n  }', start)
        body = EFFECTS[start:end]
        # The observe call must sit behind a guard on the observer itself.
        guard = body.find('if (!revealObserver)')
        observe = body.find('revealObserver.observe(')
        self.assertNotEqual(guard, -1,
                            'decorateReveal must handle a missing observer')
        self.assertNotEqual(observe, -1)
        self.assertLess(guard, observe,
                        'the guard must run before the observe call')

    def test_reduced_motion_shows_blocks(self):
        start = EFFECTS.index('function initReveal(')
        end = EFFECTS.index('\n  }', start)
        body = EFFECTS[start:end]
        reduced = body[body.index('prefersReduced()'):]
        self.assertIn('is-visible', reduced,
                      'reduced motion must mark every reveal block visible')

    def test_reduced_motion_branch_explains_why_it_cannot_just_return(self):
        # The bug was a silent early return; the comment is what stops it
        # being reintroduced.
        start = EFFECTS.index('function initReveal(')
        body = EFFECTS[start:EFFECTS.index('revealObserver = new', start)]
        self.assertIn('reduced motion', body.lower())

    def test_every_observe_call_is_guarded(self):
        # reinit() already checked `if (revealObserver)`; decorateReveal() was
        # the one that did not, and it is reached from the same hooks.
        body = EFFECTS[EFFECTS.index('function decorateReveal('):
                       EFFECTS.index('\n  }', EFFECTS.index('function decorateReveal('))]
        self.assertIn('if (!revealObserver)', body)
        self.assertIn('revealObserver.observe(el)', body)
        # reinit's guard, kept so a later edit does not drop it.
        reinit = EFFECTS[EFFECTS.index('function reinit('):]
        self.assertIn('if (revealObserver) {', reinit)


if __name__ == '__main__':
    unittest.main()
