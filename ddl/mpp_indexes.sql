-- YMatrix / Greenplum 等价访问路径索引。
-- 仅用于 indexed 配置；baseline 配置只保留分布键。
CREATE UNIQUE INDEX IF NOT EXISTS uq_region_key ON region (r_regionkey);
CREATE UNIQUE INDEX IF NOT EXISTS uq_nation_key ON nation (n_nationkey);
CREATE UNIQUE INDEX IF NOT EXISTS uq_supplier_key ON supplier (s_suppkey);
CREATE UNIQUE INDEX IF NOT EXISTS uq_customer_key ON customer (c_custkey);
CREATE UNIQUE INDEX IF NOT EXISTS uq_part_key ON part (p_partkey);
CREATE UNIQUE INDEX IF NOT EXISTS uq_partsupp_key ON partsupp (ps_partkey, ps_suppkey);
CREATE UNIQUE INDEX IF NOT EXISTS uq_orders_key ON orders (o_orderkey);
CREATE UNIQUE INDEX IF NOT EXISTS uq_lineitem_key ON lineitem (l_orderkey, l_linenumber);
CREATE INDEX IF NOT EXISTS idx_lineitem_orderkey ON lineitem (l_orderkey);
CREATE INDEX IF NOT EXISTS idx_lineitem_part_supp ON lineitem (l_partkey, l_suppkey);
CREATE INDEX IF NOT EXISTS idx_lineitem_shipdate ON lineitem (l_shipdate);
CREATE INDEX IF NOT EXISTS idx_lineitem_receipt_commit ON lineitem (l_receiptdate, l_commitdate);
CREATE INDEX IF NOT EXISTS idx_orders_custkey ON orders (o_custkey);
CREATE INDEX IF NOT EXISTS idx_orders_orderdate ON orders (o_orderdate);
CREATE INDEX IF NOT EXISTS idx_partsupp_part_supp ON partsupp (ps_partkey, ps_suppkey);
CREATE INDEX IF NOT EXISTS idx_supplier_nationkey ON supplier (s_nationkey);
CREATE INDEX IF NOT EXISTS idx_customer_nationkey ON customer (c_nationkey);
CREATE INDEX IF NOT EXISTS idx_nation_regionkey ON nation (n_regionkey);
CREATE INDEX IF NOT EXISTS idx_part_type_key ON part (p_type, p_partkey);
CREATE INDEX IF NOT EXISTS idx_part_name_pattern ON part (p_name text_pattern_ops);
ANALYZE;
