-- Dimensões de cliente (KNA1) e de centro/filial (T001W).
CREATE OR REPLACE VIEW dim_cliente AS
SELECT
    LTRIM(KUNNR, '0')  AS cliente,      -- conversão ALPHA
    NAME1              AS nome,
    ORT01              AS cidade,
    REGIO              AS uf
FROM stg_kna1;

CREATE OR REPLACE VIEW dim_centro AS
SELECT
    WERKS  AS centro,
    NAME1  AS nome,
    ORT01  AS cidade,
    REGIO  AS uf
FROM stg_t001w;
