# SPDX-License-Identifier: GPL-2.0-only
"""Trusted measurement overlay, applied equally to immutable baseline/candidate snapshots."""
import pathlib,sys
p=pathlib.Path(sys.argv[1])/"mm/swapfile.c";s=p.read_text()
def replace(a,b):
 global s
 if s.count(a)!=1: raise SystemExit("overlay anchor not unique: "+a[:80])
 s=s.replace(a,b)
replace("static struct kmem_cache *swap_table_cachep;", """static struct kmem_cache *swap_table_cachep;
/* Controller-only pilot telemetry: requested bytes, not physical RAM. */
static atomic_long_t sn_meta_live = ATOMIC_LONG_INIT(0);
static atomic_long_t sn_meta_peak = ATOMIC_LONG_INIT(0);
static atomic_long_t sn_extend_allocs = ATOMIC_LONG_INIT(0);
static atomic_long_t sn_extend_checks = ATOMIC_LONG_INIT(0);
static atomic_long_t sn_extend_retained = ATOMIC_LONG_INIT(0);
static void sn_meta_add(long delta)
{
	long now = atomic_long_add_return(delta, &sn_meta_live);
	long old = atomic_long_read(&sn_meta_peak);
	while (now > old) {
		long seen = atomic_long_cmpxchg(&sn_meta_peak, old, now);
		if (seen == old)
			break;
		old = seen;
	}
}
static int sn_metrics_show(struct seq_file *m, void *v)
{
	seq_printf(m, "requested_live_bytes %ld\\nrequested_peak_bytes %ld\\nextend_allocs %ld\\nextend_checks %ld\\n",
		   atomic_long_read(&sn_meta_live), atomic_long_read(&sn_meta_peak),
		   atomic_long_read(&sn_extend_allocs), atomic_long_read(&sn_extend_checks));
	seq_printf(m, "cluster_slots %lu\\ninline_count_max %lu\\n", (unsigned long)SWAPFILE_CLUSTER, (unsigned long)SWP_TB_COUNT_MAX);
	seq_printf(m, "extend_retained %ld\\n", atomic_long_read(&sn_extend_retained));
	return 0;
}
static int __init sn_metrics_init(void)
{
	return proc_create_single("swap_next_metrics", 0444, NULL, sn_metrics_show) ? 0 : -ENOMEM;
}
late_initcall(sn_metrics_init);
""")
replace("folio = page_folio(container_of(head, struct page, rcu_head));",
        "folio = page_folio(container_of(head, struct page, rcu_head));\n\tsn_meta_add(-PAGE_SIZE);")
replace("\t\tkmem_cache_free(swap_table_cachep, table);",
        "\t\tsn_meta_add(-(long)sizeof(*table));\n\t\tkmem_cache_free(swap_table_cachep, table);")
replace("\trcu_assign_pointer(ci->table, table);",
        "\tsn_meta_add(SWP_TABLE_USE_PAGE ? PAGE_SIZE : sizeof(*table));\n\trcu_assign_pointer(ci->table, table);")
replace("\tkfree(ci->memcg_table);","\tif (ci->memcg_table)\n\t\tsn_meta_add(-(long)sizeof(*ci->memcg_table));\n\tkfree(ci->memcg_table);")
replace("\t\tci->memcg_table = kzalloc_obj(*ci->memcg_table, gfp);",
        "\t\tci->memcg_table = kzalloc_obj(*ci->memcg_table, gfp);\n\t\tif (ci->memcg_table)\n\t\t\tsn_meta_add(sizeof(*ci->memcg_table));")
replace("\tkfree(ci->zero_bitmap);",
        "\tif (ci->zero_bitmap)\n\t\tsn_meta_add(-(long)(BITS_TO_LONGS(SWAPFILE_CLUSTER) * sizeof(unsigned long)));\n\tkfree(ci->zero_bitmap);")
replace("\tci->zero_bitmap = bitmap_zalloc(SWAPFILE_CLUSTER, gfp);",
        "\tci->zero_bitmap = bitmap_zalloc(SWAPFILE_CLUSTER, gfp);\n\tif (ci->zero_bitmap)\n\t\tsn_meta_add(BITS_TO_LONGS(SWAPFILE_CLUSTER) * sizeof(unsigned long));")
replace("\tspin_lock(&ci->lock);\n\t/*\n\t * Extend table allocation",
        "\tsn_meta_add(sizeof(ci->extend_table[0]) * SWAPFILE_CLUSTER);\n\tatomic_long_inc(&sn_extend_allocs);\n\tspin_lock(&ci->lock);\n\t/*\n\t * Extend table allocation")
replace("out_free:\n\tspin_unlock(&ci->lock);\n\tkfree(table);",
        "out_free:\n\tspin_unlock(&ci->lock);\n\tsn_meta_add(-(long)(sizeof(ci->extend_table[0]) * SWAPFILE_CLUSTER));\n\tkfree(table);")
# Identical anchor whether candidate uses an early return or a boolean flag.
replace("\tkfree(ci->extend_table);",
        "\tsn_meta_add(-(long)(sizeof(ci->extend_table[0]) * SWAPFILE_CLUSTER));\n\tkfree(ci->extend_table);")
replace("\tif (!ci->extend_table)\n\t\treturn;",
        "\tatomic_long_inc(&sn_extend_checks);\n\tif (!ci->extend_table)\n\t\treturn;")
replace("\tkvfree(cluster_info);",
        "\tsn_meta_add(-(long)(nr_clusters * sizeof(*cluster_info)));\n\tkvfree(cluster_info);")
replace("\tfor (i = 0; i < nr_clusters; i++)\n\t\tspin_lock_init",
        "\tsn_meta_add(nr_clusters * sizeof(*cluster_info));\n\tfor (i = 0; i < nr_clusters; i++)\n\t\tspin_lock_init")
if "\tbool can_free = true;" in s:
 replace("\tif (can_free) {", "\tif (!can_free)\n\t\tatomic_long_inc(&sn_extend_retained);\n\tif (can_free) {")
else:
 replace("\t\tif (ci->extend_table[i])\n\t\t\treturn;", "\t\tif (ci->extend_table[i]) {\n\t\t\tatomic_long_inc(&sn_extend_retained);\n\t\t\treturn;\n\t\t}")
p.write_text(s)
