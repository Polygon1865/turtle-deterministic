"""Tushare field maps.

A-share statements are already columnar, so the map is mostly identity.
HK statements arrive as ``ind_name`` / ``ind_value`` line items and must be
pivoted onto the canonical item names.
"""

from __future__ import annotations

# Canonical item -> Tushare column (A-share)
CN_INCOME_MAP: dict[str, str] = {
    "revenue": "revenue",
    "oper_cost": "oper_cost",
    "sell_exp": "sell_exp",
    "admin_exp": "admin_exp",
    "rd_exp": "rd_exp",
    "finance_exp": "fin_exp",
    "operate_profit": "operate_profit",
    "total_profit": "total_profit",
    "income_tax": "income_tax",
    "n_income": "n_income",
    "n_income_attr_p": "n_income_attr_p",
    "minority_gain": "minority_gain",
    "basic_eps": "basic_eps",
    "diluted_eps": "diluted_eps",
    "asset_disp_income": "asset_disp_income",
    "non_oper_income": "non_oper_income",
    "oth_income": "oth_income",
    "invest_income": "invest_income",
}

CN_BALANCE_MAP: dict[str, str] = {
    "money_cap": "money_cap",
    "trad_asset": "trad_asset",
    "accounts_receiv": "accounts_receiv",
    "inventories": "inventories",
    "total_assets": "total_assets",
    "st_borr": "st_borr",
    "lt_borr": "lt_borr",
    "bond_payable": "bond_payable",
    "non_cur_liab_due_1y": "non_cur_liab_due_1y",
    "total_liab": "total_liab",
    "total_hldr_eqy_exc_min_int": "total_hldr_eqy_exc_min_int",
    "minority_int": "minority_int",
    "goodwill": "goodwill",
    "contract_liab": "contract_liab",
    "adv_receipts": "adv_receipts",
}

CN_CASHFLOW_MAP: dict[str, str] = {
    "n_cashflow_act": "n_cashflow_act",
    "n_cashflow_inv_act": "n_cashflow_inv_act",
    "n_cash_flows_fnc_act": "n_cash_flows_fnc_act",
    "c_pay_acq_const_fiolta": "c_pay_acq_const_fiolta",
    "depr_fa_coga_dpba": "depr_fa_coga_dpba",
    "amort_intang_assets": "amort_intang_assets",
    "lt_amort_deferred_exp": "lt_amort_deferred_exp",
    "c_pay_dist_dpcp_int_exp": "c_pay_dist_dpcp_int_exp",
    "c_paid_for_taxes": "c_paid_for_taxes",
    "c_fr_sale_sg": "c_fr_sale_sg",
    "c_inf_fr_operate_a": "c_inf_fr_operate_a",
    "c_paid_goods_srv": "c_paid_goods_srv",
    "c_paid_to_for_empl": "c_paid_to_for_empl",
    "c_pay_oth_act": "c_pay_oth_act",
}

# Tushare column lists (what we ask the API for)
CN_INCOME_FIELDS = ",".join(CN_INCOME_MAP.values())
CN_BALANCE_FIELDS = ",".join(CN_BALANCE_MAP.values())
CN_CASHFLOW_FIELDS = ",".join(CN_CASHFLOW_MAP.values())

# ---------------------------------------------------------------------------
# HK: canonical item -> Chinese line-item name used by hk_income / hk_balancesheet
# ---------------------------------------------------------------------------

HK_INCOME_MAP: dict[str, str] = {
    "revenue": "营业额",
    "oper_cost": "营运支出",
    "sell_exp": "销售及分销费用",
    "admin_exp": "行政开支",
    "operate_profit": "经营溢利",
    "invest_income": "应占联营公司溢利",
    "finance_exp": "融资成本",
    "total_profit": "除税前溢利",
    "income_tax": "税项",
    "n_income": "除税后溢利",
    "n_income_attr_p": "股东应占溢利",
    "minority_gain": "少数股东损益",
    "basic_eps": "每股基本盈利",
    "diluted_eps": "每股摊薄盈利",
}

HK_BALANCE_MAP: dict[str, str] = {
    "money_cap": "现金及等价物",
    "accounts_receiv": "应收帐款",
    "prepayments": "预付款项",
    "inventories": "存货",
    "total_cur_assets": "流动资产合计",
    "fix_assets": "物业厂房及设备",
    "intang_assets": "无形资产",
    "total_assets": "总资产",
    "acct_payable": "应付帐款",
    "contract_liab": "递延收入(流动)",
    "st_borr": "短期贷款",
    "total_cur_liab": "流动负债合计",
    "lt_borr": "长期贷款",
    "bond_payable": "应付票据(非流动)",
    "total_liab": "总负债",
    "total_hldr_eqy_exc_min_int": "股东权益",
    "minority_int": "少数股东权益",
}

HK_CASHFLOW_MAP: dict[str, str | tuple[str, ...]] = {
    "n_cashflow_act": "经营业务现金净额",
    "n_cashflow_inv_act": "投资业务现金净额",
    "n_cash_flows_fnc_act": "融资业务现金净额",
    "c_pay_acq_const_fiolta": ("购建固定资产", "购建无形资产及其他资产"),
    "depr_fa_coga_dpba": "加:折旧及摊销",
    "c_pay_dist_dpcp_int_exp": "已付股息(融资)",
    "c_paid_for_taxes": "已付税项",
}

HK_LINE_ITEM_FIELDS = "ts_code,end_date,ind_name,ind_value"

# Repurchase and pledge are A-share only; HK counterparts are not applicable.
