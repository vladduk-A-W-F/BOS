# UXD01-PROVENANCE-QA v2: корекція oracle

## Межа

Після незалежного підтвердження дефекту oracle дозволена лише корекція
`allStringLiterals()` у QA harness. Product source, canonical дерево,
цільовий commit, UI expectations і source pins не змінювалися.

## Першопричина v1

Спроба `1/3` завершилася `exit 1` на label `Джерело`. Babel AST подає
видимий текст елементів `dt` як `JSXText`, а v1 collector враховував лише
`StringLiteral`. Отже, це дефект oracle, не підтверджений дефект UI.

Заморожені v1 докази: `run1/receipt.json`, SHA-256
`59a99c1579beb7fcb69552a2c86c7d1d8d2bf0ed6cf3e173c9f3167d4ca481da`;
`run1/stderr.raw.txt`, SHA-256
`6ca1aa4792db9797727e9d721d563664fb58c5f37056e1d783d625eac592e1ba`.

## Зміна v2

`disclosureDtLabels(disclosure)` обходить лише єдиний уже перевірений
`.bos-monitor-disclosure`, відбирає тільки `dt` і тільки його прямі,
trimmed `JSXText` children. Десять погоджених labels, усі інші AST
assertions, clean-HEAD/source-hash guards та source pins збережено.

Виключено навмисно: глобальний пошук JSX text, послаблення expected labels,
зміни source, React/DOM mount, Node execution, parser import, build, HTTP,
БД, browser та повний suite.

## Точні артефакти v2

- `uxd01_provenance_test.cjs`: SHA-256
  `fc43cf5bbb0fd49912dfdb7f40f5af47c0cd535425238562fbcda15cf00d7b6b`.
- `SCOPE_RU.md`: SHA-256
  `6ea974f4222caa84f7f2e198f464c6ef3381996e2d0e406566a7da5cd6a34a61`.
- Незмінний target: commit
  `0338cc026a91f1aadc0f41ebf6cff812f72d7086`; source SHA-256
  `cc97bee6d680df1bc4aedd6a3a6892b3283a17434867b268c11d38010b1732e7`.

## Стан

Жодного виконання v2 не було. Спроба `1/3` збережена; спроба `2/3` можлива
лише після нового незалежного review exact v2 files і окремого root GO.
