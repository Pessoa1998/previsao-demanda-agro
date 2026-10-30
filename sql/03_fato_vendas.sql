-- Fato de itens de ordem de venda (VBAK x VBAP): uma linha por item de documento.
--   1. remove a duplicidade da carga delta pela chave do item (VBELN + POSNR);
--   2. converte DATS (AAAAMMDD) em DATE e tira os zeros à esquerda (ALPHA);
--   3. classifica o movimento, que decide o que entra na demanda.
CREATE OR REPLACE VIEW fato_vendas AS
WITH itens AS (
    SELECT
        p.*,
        ROW_NUMBER() OVER (PARTITION BY p.VBELN, p.POSNR ORDER BY p.VBELN) AS ocorrencia
    FROM stg_vbap AS p
)
SELECT
    LTRIM(k.VBELN, '0')                       AS documento,
    CAST(i.POSNR AS INTEGER)                  AS item,
    STRPTIME(k.ERDAT, '%Y%m%d')::DATE         AS data_pedido,
    k.AUART                                   AS tipo_ordem,
    LTRIM(k.KUNNR, '0')                       AS cliente,
    LTRIM(i.MATNR, '0')                       AS material,
    i.WERKS                                   AS centro,
    CAST(i.KWMENG AS DECIMAL(15, 3))          AS quantidade,
    i.VRKME                                   AS unidade,
    CAST(i.NETWR AS DECIMAL(15, 2))           AS valor_liquido,
    NULLIF(i.ABGRU, '')                       AS motivo_recusa,
    CASE
        WHEN NULLIF(i.ABGRU, '') IS NOT NULL THEN 'RECUSADO'
        WHEN k.AUART = 'ZDEV'                THEN 'DEVOLUCAO'
        WHEN k.AUART = 'ZBON'                THEN 'BONIFICACAO'
        ELSE 'VENDA'
    END                                       AS movimento
FROM itens AS i
JOIN stg_vbak AS k ON k.VBELN = i.VBELN
WHERE i.ocorrencia = 1;
