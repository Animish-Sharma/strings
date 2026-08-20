# Generator doctrine — archival

You build the dossier and drive it through the adapter. The dossier is not an
essay and not a bibliography: it is a graph.

## What the dossier has to contain

| Part | Exists so that |
|---|---|
| `sources[]` with `derives_from` | the chains can be followed home |
| `origin` on each source | roots sharing an author or archive can be merged |
| `date` on each source | a chain running backwards is detectable |
| `shelfmark` or identifier | someone else can go and look at it |
| `interest` on each root | uniform stake is detectable |
| `language`, `transformations` | the wording's journey is visible |
| `supporting_sources[]` | the claim names what it rests on, not everything read |
| `archive_coverage` | absence means something |
| `what_the_record_would_look_like_if_false` | the dossier discriminates |

## The one field people get wrong

`derives_from` is not "cites". It is "takes this claim from". A chronicle citing
a register for a different fact does not derive from it for this one, and
recording it as though it does invents a cascade that is not there. Recording the
reverse — omitting a real derivation — invents independence, which is the more
dangerous error and the one the adapter cannot detect.

Where a derivation is uncertain, declare it. An uncertain edge included costs you
apparent support; an uncertain edge omitted costs the claim its meaning.

## Submitting

```bash
python3 scripts/availability.py --tier triangulation --bundle dossier.json
python3 scripts/check.py --artifact dossier.json --claim claim.json --tier triangulation --json
```

The refute-attempt gate is the collapse itself. If the count comes back below
what the claim asserts, stop. Do not add sources until the number rises — adding
a fourth copy of the same chronicle raises nothing, and adding one that does
raise it means the claim should have said so from the start, which is a new claim
with a new hash.

## What you may not do

- **Edit the frozen claim.** Lowering `claimed_independent_support` to match the
  collapse is the archival version of narrowing to the donors where it worked.
- **Accept your own dossier.** You build; you never admit.
- **Report a single origin with plural wording.** "Sources record" needs sources.

## Wording

See `doctrine/report_language.md`. Documented, attested, and occurred are three
different statements, and the prose crosses between them for free unless someone
is checking.
