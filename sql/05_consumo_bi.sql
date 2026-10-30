-- Camada de consumo para BI (o que o Power BI leria via ODBC/conexão ao Datasphere).

-- Preço médio realizado por material, usado para valorizar previsão e estoque.
CREATE OR REPLACE VIEW preco_material AS
SELECT
    material,
    SUM(valor_liquido) / NULLIF(SUM(quantidade), 0)  AS preco_medio
FROM fato_vendas
WHERE movimento = 'VENDA'
GROUP BY material;

-- KPIs mensais por família e filial.
CREATE OR REPLACE VIEW kpi_mensal AS
SELECT
    DATE_TRUNC('month', f.data_pedido)::DATE                                  AS mes,
    m.familia,
    f.centro,
    SUM(f.valor_liquido) FILTER (WHERE f.movimento = 'VENDA')                 AS valor_vendido,
    COALESCE(SUM(f.valor_liquido) FILTER (WHERE f.movimento = 'DEVOLUCAO'), 0) AS valor_devolvido,
    COUNT(DISTINCT f.documento) FILTER (WHERE f.movimento = 'VENDA')          AS pedidos,
    COUNT(DISTINCT f.cliente) FILTER (WHERE f.movimento = 'VENDA')            AS clientes_ativos
FROM fato_vendas AS f
JOIN dim_material AS m USING (material)
GROUP BY 1, 2, 3;
