cd "F:\test"

*===============================================================================
* 统一表格输出：esttab 写入同一份 RTF（首表 replace，其余 append）
* 依赖：ssc install estout
* 仅展示核心解释变量系数（不展示控制变量）：用 keep(...) 限定
*===============================================================================
global RESULTS_RTF "复现_results.rtf"

* 辅助程序：表底 FE/控制/聚类（与本 do 中 absorb 设定一致；宏名 tbc_* 避免与 e() 冲突）
* 维度说明：county=县级 code_x；town=乡镇代码_yy；provy=年份×省份 i.year#i.区县_省级码；year=单独年份 FE
capture program drop add_fe_table
program define add_fe_table
    syntax , ctrl(str) county(str) town(str) provy(str) yearfe(str) clust(str)
    estadd local tbc_controls "`ctrl'"
    estadd local tbc_county_fe "`county'"
    estadd local tbc_township_fe "`town'"
    estadd local tbc_prov_y_fe "`provy'"
    estadd local tbc_year_fe "`yearfe'"
    estadd local tbc_cluster "`clust'"
end

* 公共 esttab 选项（与论文复现范式一致）
local etab_base b(%9.3f) t(%9.3f) star(* 0.10 ** 0.05 *** 0.01) compress nogaps nonumbers note("括号内为t值。")

*---- 表底 stats()：按 Ben Jann estout 手册（help estout / Summary statistics）----
* 1) esttab 为 estout 的封装，选项传给 estout（见 repec.sowi.unibe.ch/stata/estout/esttab.html）。
* 2) stats(scalarlist[, fmt() labels() ...])：scalarlist 可为 e() 标量（如 N、r2），也可为 e() 字符串宏；
*    用 estadd local 写入的宏会进入 e()，再在 stats() 中写宏名即可（同手册：Use estadd to add...）。
* 3) labels 示例与手册一致：stats(r2_a N, labels("Adj. R-Square" "Number of Cases"))（help estout 原文）。
* 4) 选项之间须用逗号分隔：上一选项写完后接 , stats(...)；勿把整条 stats 塞进易截断的 global。

********************************************************************************
*数据转换、基本处理
//
// import delimited "township_enterprise_counts_by_year_with_division.csv",clear
// rename n 乡村创业活动 
// keep if 年份 > 2011 & 年份 < 2022
// drop 区县_备注
// save 乡村创业活动,replace
//
// import delimited "anther_data_enterprise\township_enterprise_counts_by_year_csv_2000_2022_with_division.csv",clear
// rename n 乡村创业活动1 
// keep if 年份 > 2011 & 年份 < 2022
// drop 区县_备注
// save 乡村创业活动1,replace

import delimited "township_poi_panel_2012_2021_wide.csv", clear 

gen 基层公共产品供给 = 基本公共服务 + 普惠性非基本公共服务 + 生活服务

merge 1:1 年份 code using 乡村创业活动
drop _merge
replace 乡村创业活动 = 0 if 乡村创业活动 ==.

merge 1:1 年份 code using 乡村创业活动1
drop _merge
replace 乡村创业活动1 = 0 if 乡村创业活动1 ==.

********************************************************************************
//参照论文：筛除"街道""城关镇""中心镇", 筛除：乡村创业活动和基层公共产品供给为0
gen iszhen= 0 if strpos( name, "街道")!=0
replace iszhen= 0 if strpos( name, "城关镇")!=0
replace iszhen= 0 if strpos( name, "中心镇")!=0
replace iszhen = 1 if iszhen ==.
drop if iszhen == 0
drop if 乡村创业活动 == 0
drop if 基层公共产品供给 == 0

format %14.0g code
gen long code_x = floor(code/1000)
gen year_x = 年份

merge 1:1 code_x year_x using main
drop _merge
gen ln_乡村创业活动 = ln(乡村创业活动+1)
gen ln_乡村创业活动1 = ln(乡村创业活动1+1)
gen ln_基层公共产品供给 = ln(基层公共产品供给+1)

*--- 表1：全国工商匹配（OLS / reghdfe）---
reg ln_基层公共产品供给 ln_乡村创业活动
add_fe_table, ctrl("否") county("否") town("否") provy("否") yearfe("否") clust("区县级")
estimates store m1

gen year = year_x

gen tt = year-1992
gen mean_dem_t = mean_dem*tt
gen mean_slope_t = mean_slope*tt
gen area_t = area*tt
gen dist_t =  near_dist*tt

gen mean_dem_t2 = mean_dem*tt*tt
gen mean_slope_t2 = mean_slope*tt*tt
gen area_t2 = area*tt*tt
gen dist_t2 =  near_dist*tt*tt

gen mean_dem_t3 = mean_dem*tt*tt*tt
gen mean_slope_t3 = mean_slope*tt*tt*tt
gen area_t3 = area*tt*tt*tt
gen dist_t3 =  near_dist*tt*tt*tt

global Control 玉米 水稻 小麦 mean_xx sum_yy mean_dem_t mean_slope_t area_t dist_t mean_dem_t2 mean_slope_t2 area_t2 dist_t2 mean_dem_t3 mean_slope_t3 area_t3 dist_t3

reg ln_基层公共产品供给 ln_乡村创业活动 $Control
add_fe_table, ctrl("是") county("否") town("否") provy("否") yearfe("否") clust("区县级")
estimates store m2

reghdfe ln_基层公共产品供给 ln_乡村创业活动 $Control,absorb(year code_x) vce(cluster 区县_县级码)
* absorb: 年份 + 县级 code_x（无乡镇、无年×省交互）
add_fe_table, ctrl("是") county("是") town("否") provy("否") yearfe("是") clust("区县级")
estimates store m3

esttab m1 m2 m3 using "$RESULTS_RTF", replace `etab_base' ///
    keep(ln_乡村创业活动) ///
    title("表1：基准回归（全国工商匹配）") ///
    mtitles("(1)" "(2)" "(3)") ///
    stats(tbc_controls tbc_county_fe tbc_township_fe tbc_prov_y_fe tbc_year_fe tbc_cluster N r2, ///
        fmt(%9s %9s %9s %9s %9s %9s %9.0f %9.3f) ///
        labels("控制变量" "县级FE" "乡镇FE" "年份-省份FE" "年份FE" "聚类层级" "观测值" "R-squared"))

reghdfe ln_基层公共产品供给 ln_乡村创业活动 $Control,absorb(code_x  i.year#i.区县_省级码) vce(cluster 区县_县级码)
* absorb: 县级 code_x + 年份×省份（单独年份由年×省吸收，故年份FE标为否）
add_fe_table, ctrl("是") county("是") town("否") provy("是") yearfe("否") clust("区县级")
estimates store m4

esttab m4 using "$RESULTS_RTF", append `etab_base' ///
    keep(ln_乡村创业活动) ///
    title("表2：高维固定效应（全国工商匹配）") ///
    mtitles("(1)") ///
    stats(tbc_controls tbc_county_fe tbc_township_fe tbc_prov_y_fe tbc_year_fe tbc_cluster N r2, ///
        fmt(%9s %9s %9s %9s %9s %9s %9.0f %9.3f) ///
        labels("控制变量" "县级FE" "乡镇FE" "年份-省份FE" "年份FE" "聚类层级" "观测值" "R-squared"))
****************************************************************

*--- 表3：1223 CSV 匹配 ---
reg ln_基层公共产品供给 ln_乡村创业活动1 $Control
add_fe_table, ctrl("是") county("否") town("否") provy("否") yearfe("否") clust("区县级")
estimates store m5

reghdfe ln_基层公共产品供给 ln_乡村创业活动1 $Control,absorb(year code_x) vce(cluster 区县_县级码)
add_fe_table, ctrl("是") county("是") town("否") provy("否") yearfe("是") clust("区县级")
estimates store m6

reghdfe ln_基层公共产品供给 ln_乡村创业活动1 $Control,absorb(code_x  i.year#i.区县_省级码) vce(cluster 区县_县级码)
add_fe_table, ctrl("是") county("是") town("否") provy("是") yearfe("否") clust("区县级")
estimates store m7

esttab m5 m6 m7 using "$RESULTS_RTF", append `etab_base' ///
    keep(ln_乡村创业活动1) ///
    title("表3：基准回归（1223 CSV 匹配）") ///
    mtitles("(1)" "(2)" "(3)") ///
    stats(tbc_controls tbc_county_fe tbc_township_fe tbc_prov_y_fe tbc_year_fe tbc_cluster N r2, ///
        fmt(%9s %9s %9s %9s %9s %9s %9.0f %9.3f) ///
        labels("控制变量" "县级FE" "乡镇FE" "年份-省份FE" "年份FE" "聚类层级" "观测值" "R-squared"))

// 工具变量
//ssc install ivreghdfe,replace
//net install reghdfe, replace from("https://raw.githubusercontent.com/sergiocorreia/reghdfe/master/src/")
//ssc install require
//net install ftools, replace from("https://raw.githubusercontent.com/sergiocorreia/ftools/master/src/")

merge m:1 乡镇代码_yy using "./IV"
gen lnivs = ln(总和)
gen ivs = lnivs*t

*--- 表4：工具变量 ---
ivreghdfe ln_基层公共产品供给 $Control (ln_乡村创业活动 = ivs) ,a(乡镇代码_yy i.year#i.区县_省级码) vce(cluster 区县_县级码) first
* absorb: 乡镇 + 年份×省份（无县级 code_x）
add_fe_table, ctrl("是") county("否") town("是") provy("是") yearfe("否") clust("区县级")
estimates store m8

duplicates list year 乡镇代码_yy
********************************************************************************
ivreghdfe ln_基层公共产品供给 $Control (ln_乡村创业活动1 = ivs) ,a(乡镇代码_yy i.year#i.区县_省级码) vce(cluster 区县_县级码) first
add_fe_table, ctrl("是") county("否") town("是") provy("是") yearfe("否") clust("区县级")
estimates store m9

esttab m8 m9 using "$RESULTS_RTF", append `etab_base' ///
    keep(ln_乡村创业活动 ln_乡村创业活动1) ///
    title("表4：工具变量（2SLS）") ///
    mtitles("全国工商" "1223 CSV") ///
    stats(tbc_controls tbc_county_fe tbc_township_fe tbc_prov_y_fe tbc_year_fe tbc_cluster N r2, ///
        fmt(%9s %9s %9s %9s %9s %9s %9.0f %9.3f) ///
        labels("控制变量" "县级FE" "乡镇FE" "年份-省份FE" "年份FE" "聚类层级" "观测值" "R-squared"))

//双重差分
drop if 乡镇代码_yy ==.
merge 1:1 year 乡镇代码_yy using ".\did", keep(match) nogen
gen dd = 1 if 成立年份>=post
replace dd = 0 if 成立年份<post
gen dis_year = year-post

*--- 表5：DID ---
reghdfe ln_基层公共产品供给 dd 
* 无控制变量、无 FE
add_fe_table, ctrl("否") county("否") town("否") provy("否") yearfe("否") clust("区县级")
estimates store m10

reghdfe ln_基层公共产品供给 dd $Control, vce(cluster 区县_县级码)
add_fe_table, ctrl("是") county("否") town("否") provy("否") yearfe("否") clust("区县级")
estimates store m11

reghdfe ln_基层公共产品供给 dd $Control, absorb(乡镇代码_yy year) vce(cluster 区县_县级码)
* absorb: 乡镇 + 年份（无县级 code_x、无年×省）
add_fe_table, ctrl("是") county("否") town("是") provy("否") yearfe("是") clust("区县级")
estimates store m12

reghdfe ln_基层公共产品供给 dd $Control, absorb(乡镇代码_yy i.year#i.区县_省级码) vce(cluster 区县_县级码)
add_fe_table, ctrl("是") county("否") town("是") provy("是") yearfe("否") clust("区县级")
estimates store m13

esttab m10 m11 m12 m13 using "$RESULTS_RTF", append `etab_base' ///
    keep(dd) ///
    title("表5：双重差分") ///
    mtitles("(1)" "(2)" "(3)" "(4)") ///
    stats(tbc_controls tbc_county_fe tbc_township_fe tbc_prov_y_fe tbc_year_fe tbc_cluster N r2, ///
        fmt(%9s %9s %9s %9s %9s %9s %9.0f %9.3f) ///
        labels("控制变量" "县级FE" "乡镇FE" "年份-省份FE" "年份FE" "聚类层级" "观测值" "R-squared"))


*（1）生成d_j，假设你在"tab distance, missing"中发现，distance最小值是-4，那么生成过程如下：
forvalues i=1/6 { 
gen d_`i'  = 0 
replace d_`i'  = 1 if post!=. & dis_year== -`i'
}

*（2）生成dj，假设你在"tab distance, missing"中发现，distance最大值是5，那么生成过程如下：
forvalues i=1/5 { 
gen d`i'  = 0 
replace d`i'  = 1 if post!=. & dis_year== `i'
}

*（3）生成current
gen current  = 0
replace current = 1 if post!=. & dis_year== 0

*************

*--- 表6：DID 全控制 + 平行趋势 ---
reghdfe ln_基层公共产品供给 dd $Control , absorb(乡镇代码_yy i.year#i.区县_省级码) vce(cluster 区县_县级码)
add_fe_table, ctrl("是") county("否") town("是") provy("是") yearfe("否") clust("区县级")
estimates store m14

reghdfe ln_基层公共产品供给  d_6 d_5 d_4 d_3 d_2 current d1 d2 d3 d4 d5 $Control, absorb(乡镇代码_yy i.year#i.区县_省级码) vce(cluster 区县_县级码)
add_fe_table, ctrl("是") county("否") town("是") provy("是") yearfe("否") clust("区县级")
estimates store m15

esttab m14 m15 using "$RESULTS_RTF", append `etab_base' ///
    keep(dd d_6 d_5 d_4 d_3 d_2 current d1 d2 d3 d4 d5) ///
    title("表6：DID 全样本 FE 与平行趋势（事件研究）") ///
    mtitles("DID+FE" "事件研究") ///
    stats(tbc_controls tbc_county_fe tbc_township_fe tbc_prov_y_fe tbc_year_fe tbc_cluster N r2, ///
        fmt(%9s %9s %9s %9s %9s %9s %9.0f %9.3f) ///
        labels("控制变量" "县级FE" "乡镇FE" "年份-省份FE" "年份FE" "聚类层级" "观测值" "R-squared"))

//图（单独导出）
coefplot,keep(d_6 d_5 d_4 d_3 d_2 current d1 d2 d3 d4 d5 ) levels(95) vertical lcolor(black) mcolor(black) msymbol(circle_hollow) ytitle(回归系数, size(small))  ylabel(, labsize(small) angle(horizontal) nogrid) yline(0, lwidth(vthin)lpattern(solid) lcolor(black)) xtitle(政策实施相对时间, size(small)) xlabel(,labsize(small))  graphregion(fcolor(white) lcolor(white) ifcolor(white) ilcolor(white)) ciopts(recast(rcap)) xline(11.5, lwidth(vthin) lpattern(solid)lcolor(black)) addplot(line @b @at)  xline(6,lwidth(vthin)lpattern(dash)lcolor(red))

*===============================================================================
* 运行结束后打开：$RESULTS_RTF （当前工作目录，默认 F:\test）
*===============================================================================
