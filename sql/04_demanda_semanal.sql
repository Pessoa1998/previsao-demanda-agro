-- Demanda firme semanal por material x centro (semana começa na segunda-feira).
-- Regra de negócio: demanda = venda + bonificação (as duas consomem estoque).
-- Devoluções e itens recusados não representam demanda nova e ficam de fora.
-- Semanas sem pedido entram com zero: série densa, pronta para o modelo.
CREATE OR REPLACE TABLE demanda_semanal AS
WITH firme AS (
    SELECT
        DATE_TRUNC('week', data_pedido)::DATE  AS semana,
        material,
        centro,
        SUM(quantidade)                        AS quantidade
    FROM fato_vendas
    WHERE movimento IN ('VENDA', 'BONIFICACAO')
    GROUP BY 1, 2, 3
),
calendario AS (
    SELECT CAST(t.s AS DATE) AS semana
    FROM GENERATE_SERIES(
        (SELECT MIN(semana) FROM firme)::TIMESTAMP,
        (SELECT MAX(semana) FROM firme)::TIMESTAMP,
        INTERVAL 7 DAY
    ) AS t(s)
),
series AS (
    SELECT DISTINCT material, centro FROM firme
)
SELECT
    c.semana,
    s.material,
    s.centro,
    CAST(COALESCE(f.quantidade, 0) AS DOUBLE)  AS quantidade
FROM calendario AS c
CROSS JOIN series AS s
LEFT JOIN firme AS f
       ON f.semana = c.semana
      AND f.material = s.material
      AND f.centro = s.centro
ORDER BY s.material, s.centro, c.semana;
