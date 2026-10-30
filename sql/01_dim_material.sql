-- Dimensão de materiais: MARA + MAKT (texto em português) + T023T (família).
-- No SAP Datasphere seria uma view de dimensão com associação de textos.
CREATE OR REPLACE VIEW dim_material AS
SELECT
    LTRIM(m.MATNR, '0')                    AS material,          -- conversão ALPHA
    t.MAKTX                                AS descricao,
    m.MATKL                                AS grupo_mercadoria,
    g.WGBEZ                                AS familia,
    m.MEINS                                AS unidade,
    STRPTIME(m.ERSDA, '%Y%m%d')::DATE      AS criado_em,          -- DATS -> DATE
    COALESCE(m.LVORM, '') = 'X'            AS marcado_eliminacao
FROM stg_mara AS m
LEFT JOIN stg_makt  AS t ON t.MATNR = m.MATNR AND t.SPRAS = 'P'   -- MAKT tem 1 linha por idioma
LEFT JOIN stg_t023t AS g ON g.MATKL = m.MATKL AND g.SPRAS = 'P';
