# Example packets

Real packets from a real run against the **fixture** pack, not curated examples.

A curated example is maintained alongside its schema and drifts with it. These
came out of an actual campaign that was admitted, so if they had drifted the run
would have failed first.

They come from the fixture pack rather than from a registered field on purpose.
An example packet carrying a field's vocabulary puts that vocabulary in a frame
directory, and the purity check refuses it — correctly, and it refused this
directory's first version. A pack's own example packets belong in that pack.

`scripts/check_schema_examples.py` validates each against its schema. Their job
is to make the schemas testable: a schema nothing has ever satisfied can require
a field no producer writes and validate zero packets forever without saying so.
That is not hypothetical here — it is how the shared validator was found unable
to read a type union its own state schema uses, and how the claim schema was
found requiring two fields no author supplies.

Regenerate by re-running the campaign and copying its workdir. Do not hand-edit:
a packet edited to satisfy a schema is the curated example this directory exists
to avoid.
