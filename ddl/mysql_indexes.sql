-- MySQL 单机版等价访问路径索引。
-- 仅用于 indexed 配置；baseline 配置不执行本文件。
CREATE UNIQUE INDEX uq_region_key ON region (r_regionkey);
CREATE UNIQUE INDEX uq_nation_key ON nation (n_nationkey);
CREATE UNIQUE INDEX uq_supplier_key ON supplier (s_suppkey);
CREATE UNIQUE INDEX uq_customer_key ON customer (c_custkey);
CREATE UNIQUE INDEX uq_part_key ON part (p_partkey);
CREATE UNIQUE INDEX uq_partsupp_key ON partsupp (ps_partkey, ps_suppkey);
CREATE UNIQUE INDEX uq_orders_key ON orders (o_orderkey);
CREATE UNIQUE INDEX uq_lineitem_key ON lineitem (l_orderkey, l_linenumber);
CREATE INDEX idx_lineitem_orderkey ON lineitem (l_orderkey);
CREATE INDEX idx_lineitem_part_supp ON lineitem (l_partkey, l_suppkey);
CREATE INDEX idx_lineitem_shipdate ON lineitem (l_shipdate);
CREATE INDEX idx_lineitem_receipt_commit ON lineitem (l_receiptdate, l_commitdate);
CREATE INDEX idx_orders_custkey ON orders (o_custkey);
CREATE INDEX idx_orders_orderdate ON orders (o_orderdate);
CREATE INDEX idx_partsupp_part_supp ON partsupp (ps_partkey, ps_suppkey);
CREATE INDEX idx_supplier_nationkey ON supplier (s_nationkey);
CREATE INDEX idx_customer_nationkey ON customer (c_nationkey);
CREATE INDEX idx_nation_regionkey ON nation (n_regionkey);
CREATE INDEX idx_part_type_key ON part (p_type, p_partkey);
CREATE INDEX idx_part_name ON part (p_name);
ANALYZE TABLE region, nation, supplier, customer, part, partsupp, orders, lineitem;
