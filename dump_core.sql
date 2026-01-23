-- Экспорт основных таблиц с данными
\copy alembic_version TO 'alembic_version.csv' WITH CSV HEADER;
\copy rarities        TO 'rarities.csv'        WITH CSV HEADER;
\copy tokens          TO 'tokens.csv'          WITH CSV HEADER;
\copy cards           TO 'cards.csv'           WITH CSV HEADER;
