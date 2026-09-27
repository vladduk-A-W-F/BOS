# Dev.5 package: первоначальное review

27.09.2026. Reviewer `/root/bos3_candidate_review`.
Author package `0a1246347fc7c4d7f0db128ff61b28d4d793370b`.
Verdict: **REVISE_EVIDENCE_ONLY**, один P1.

PACK_MANIFEST.json и AUTHOR_REPORT_RU.md заявляют pdftoppm exit0 и
pdf-render.raw.txt, но этот raw файл отсутствует в tree/commit.
Три PNG существуют и независимо визуально просмотрены; это не заменяет
receipt заявленной команды/exit. Recover только original raw evidence,
если оно действительно сохранено. Иначе исправить exit на UNCONFIRMED,
сохранив только фактическое наблюдение существующих изображений.
Никакого нового рендера для производства отсутствующей квитанции.

Остальные сведения подтверждены: clean package, пять разрешённых files
плюс evidence, dev.5 version/README/PDF/manifest, PDF SHA
d38196bd3d45aa80023bf66e136f83a194746c8d667eb5ff97ae35e698a9de01,
четыре UI blobs и registry unchanged. A5AD applicability inputs/hashes/
tree/блобы согласованы, 3 сценария/8UXD/11gates сохранены. Старые delivery
и browser proof не перенесены. Исправление поручено прежнему автору
отдельной B30-UXD03-PACK-EVIDENCE-P1, без изменений product или повторов.
