# Programmable Analytics

Analytics for the Programmable ecosystem.

[Dashboard](https://dune.com/programmablehq/analytics) · [Website](https://programmable.market) · [X](https://x.com/ProgrammableHQ) · [Discord](https://discord.com/invite/programmable) · [DEX Screener](https://dexscreener.com/robinhood/0x3df16f271060e4941c0386047def159f42e629dc0455db623c5b363eeacbcc1d)

## Dashboard

The dashboard currently has three cards, all powered by [one query](https://dune.com/queries/8626416):

| Metric | Definition |
| --- | --- |
| V4 burned | Total V4 transferred to the burn address |
| Supply burned | Burned V4 as a percentage of the original 1 billion supply |
| Burn transactions | Number of distinct finalized burn transactions |

Dune refreshes the data once a day, in the 21:30–22:00 UTC window. GitHub manages the query source; it does not run an additional data refresh.

The repository can grow as more ecosystem metrics are added. Only the three metrics above are currently published.

## Data

- Network: Robinhood Chain, chain ID `4663`.
- V4: [`0xC60bA256B44334A0Cd2C7242E98B88f031abB006`](https://robinhoodchain.blockscout.com/token/0xC60bA256B44334A0Cd2C7242E98B88f031abB006).
- Burn address: [`0x000000000000000000000000000000000000dEaD`](https://robinhoodchain.blockscout.com/address/0x000000000000000000000000000000000000dEaD).

The query reads finalized transfer logs from the official Robinhood RPC. It uses indexed Dune timestamps when available and a block RPC lookup otherwise. Transfers are deduplicated by transaction hash and log index. Raw token amounts are retained as integers; the cards round values for display.

Transfers to the dead address remove tokens from circulation. They do not reduce the contract's `totalSupply`. RPC failures fail the refresh instead of returning a false zero.

## Maintaining queries

`dune.json` lists the managed queries and records the dashboard layout. SQL lives in `queries/`. The dashboard layout and its refresh schedule are managed in Dune; editing the layout record does not deploy widgets.

Python 3.11 or newer is sufficient. There are no third party Python dependencies.

```sh
python3 scripts/dune.py check
python3 -m unittest discover -s tests -v
```

With a `DUNE_API_KEY` in the environment:

```sh
python3 scripts/dune.py verify   # Compare local SQL with Dune
python3 scripts/dune.py pull     # Import current SQL from Dune
python3 scripts/dune.py push     # Save SQL to Dune and verify it
```

The key must belong to the `programmablehq` team and have Read/Write scope for publishing. Store it as the repository's `DUNE_API_KEY` Actions secret. Never commit it.

Changes merged into `main` are checked and then saved to the existing Dune queries. The workflow verifies the saved SQL after publishing. It checks query IDs and ownership and refuses archived, private or unsaved queries. For normal pushes it also refuses to overwrite SQL that was changed directly in Dune since the previous repository revision. To reconcile a direct Dune edit, pull it locally, review the diff and commit it.

The **Dune queries** workflow can also be run manually with `verify`, `pull` or `push`. A pull exports the current public SQL as the `dune-query-source` artifact for review and import. A manual push explicitly publishes the selected main-branch SQL. No synchronization command executes the analytics query or changes its schedule.

## Dune API

This integration uses Dune's current [Read Query](https://docs.dune.com/api-reference/queries/endpoint/read) and [Update Query](https://docs.dune.com/api-reference/queries/endpoint/update) endpoints. The [older DuneQueryRepo template](https://github.com/duneanalytics/DuneQueryRepo) is archived.
