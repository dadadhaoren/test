cd "F:\test"

********************************************************************************
*数据转换、基本处理

import delimited "township_enterprise_counts_by_year_with_division.csv",clear
rename n 乡村创业活动 
keep if 年份 > 2011 & 年份 < 2022
drop 区县_备注
save 乡村创业活动,replace


import delimited "township_poi_panel_2012_2021_wide.csv", clear 

gen 基层公共产品供给 = 基本公共服务 + 普惠性非基本公共服务 + 生活服务

merge 1:1 年份 code using 乡村创业活动
drop _merge

replace 乡村创业活动 = 0 if 乡村创业活动 ==.
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
gen ln_基层公共产品供给 = ln(基层公共产品供给+1)

reg ln_基层公共产品供给 ln_乡村创业活动

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

reghdfe ln_基层公共产品供给 ln_乡村创业活动 $Control,absorb(year code_x) vce(cluster 区县_县级码)

reghdfe ln_基层公共产品供给 ln_乡村创业活动 $Control,absorb(code_x  i.year#i.区县_省级码) vce(cluster 区县_县级码)

// 工具变量
// tab4

//ssc install ivreghdfe,replace
//net install reghdfe, replace from("https://raw.githubusercontent.com/sergiocorreia/reghdfe/master/src/")
//ssc install require
//net install ftools, replace from("https://raw.githubusercontent.com/sergiocorreia/ftools/master/src/")

merge m:1 乡镇代码_yy using "./IV"
gen lnivs = ln(总和)
gen ivs = lnivs*t

ivreghdfe ln_基层公共产品供给 $Control (ln_乡村创业活动 = ivs) ,a(乡镇代码_yy i.year#i.区县_省级码) vce(cluster 区县_县级码) first

duplicates list year 乡镇代码_yy

//双重差分
// tab5
// preserve
drop if 乡镇代码_yy ==.
merge 1:1 year 乡镇代码_yy using ".\did", keep(match) nogen
gen dd = 1 if 成立年份>=post
replace dd = 0 if 成立年份<post
gen dis_year = year-post

reghdfe ln_基层公共产品供给 dd 
outreg2 using tab5.doc,replace tstat bdec(3) tdec(3) adjr2 addtext(TOWN FE, NO,Year FE, YES, TOWN&YEAR FE, YES)

reghdfe ln_基层公共产品供给 dd $Control, vce(cluster 区县_县级码)
outreg2 using tab5.doc,append tstat bdec(3) tdec(3) adjr2 addtext(TOWN FE, NO,Year FE, NO, TOWN&YEAR FE, NO)

reghdfe ln_基层公共产品供给 dd $Control, absorb(乡镇代码_yy year) vce(cluster 区县_县级码)
outreg2 using tab5.doc,append tstat bdec(3) tdec(3) adjr2 addtext(TOWN FE, YES,Year FE, YES, TOWN&YEAR FE, NO)

reghdfe ln_基层公共产品供给 dd $Control, absorb(乡镇代码_yy i.year#i.区县_省级码) vce(cluster 区县_县级码)
outreg2 using tab5.doc,append tstat bdec(3) tdec(3) adjr2 addtext(TOWN FE, YES,Year FE, NO, TOWN&YEAR FE, YES)


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

//did
reghdfe ln_基层公共产品供给 dd $Control , absorb(乡镇代码_yy i.year#i.区县_省级码) vce(cluster 区县_县级码)

//平行趋势
reghdfe ln_基层公共产品供给  d_6 d_5 d_4 d_3 d_2 current d1 d2 d3 d4 d5 $Control, absorb(乡镇代码_yy i.year#i.区县_省级码) vce(cluster 区县_县级码)
//图
coefplot,keep(d_6 d_5 d_4 d_3 d_2 current d1 d2 d3 d4 d5 ) levels(95) vertical lcolor(black) mcolor(black) msymbol(circle_hollow) ytitle(回归系数, size(small))  ylabel(, labsize(small) angle(horizontal) nogrid) yline(0, lwidth(vthin)lpattern(solid) lcolor(black)) xtitle(政策实施相对时间, size(small)) xlabel(,labsize(small))  graphregion(fcolor(white) lcolor(white) ifcolor(white) ilcolor(white)) ciopts(recast(rcap)) xline(11.5, lwidth(vthin) lpattern(solid)lcolor(black)) addplot(line @b @at)  xline(6,lwidth(vthin)lpattern(dash)lcolor(red))
// restore









