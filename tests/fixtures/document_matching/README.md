# Synthetic invoice fixture, contract v1

`supplier-invoice.pdf` is an original single-page text PDF containing only synthetic identifiers. The actual existing `operations.documents.parse` reads its bytes through pypdf in the tests. `no-text.pdf` is a synthetic graphics-only PDF: no OCR is performed and the existing parser must report `ocr_required`.

Template header: `BOS SYNTHETIC SUPPLIER INVOICE V1`. Exact labels: Supplier EDRPOU, Invoice number, Invoice date, Currency, Tax basis, Item code, Revision, Unit, Quantity, Unit price, Line total, Invoice total. Repeated line labels are explicitly unsupported. Extracted strings and their offsets/quotes are retained verbatim. The adapter does not recognize arbitrary invoices or invoke AI.

`context.json` supplies one selected supplier, one selected item and one selected one-item Purchase, with two linked receipt movements (4 + 6). The test fills source metadata from the real PDF parse. Inputs describe a full purchase, excluding VAT, with no extras. Return quantities must be supplied by a future verified adapter from linked return sources, never inferred from remaining stock.

All context rows are synthetic DTOs. These fixtures do not prove Policy authorization, byte verification on a stored Document, a persisted exception queue, duplicate-invoice prevention, posting, payment, receipt creation or a transaction. `accept_draft` accepts only the mock draft; `operation_proposal` always remains null. Models, migration, URLs, UI and the common preview/confirm are unchanged.

The existing PDF parser has an unused top-level `Document` model import. This pure unit test supplies only that unused import with an inert stub so it can execute the real parser without Django setup or opening a database. The `parse` function, PDF reader, source bytes and extraction result are not mocked.
