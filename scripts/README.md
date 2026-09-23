# Maintainer scripts

`smoke.py` exercises the public API of an already-running server with a unique
classifier and verifies persisted unknown evidence. It intentionally appends test
data, so use a disposable local instance.

`release.py` checks workspace versions and milestone metadata without publishing.
An installer and benchmark command will be added only when real distribution
artifacts and a reviewed benchmark exist (OC-013/014).
