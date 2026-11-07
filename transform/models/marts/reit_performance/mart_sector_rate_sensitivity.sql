-- How each sector's monthly total return moved with policy rate changes.
-- A sector's return is the equal-weighted average of its REITs. Only a few months have a rate
-- change, so read the month counts alongside the averages.
with sector_months as (
    select month, sector, avg(total_return_pct) as total_return_pct
    from {{ ref('mart_reit_monthly') }}
    where total_return_pct is not null
    group by month, sector
)
select
    s.sector,
    count(*) as months,
    count(*) filter (where r.repo_change_pts > 0) as hike_months,
    count(*) filter (where r.repo_change_pts < 0) as cut_months,
    avg(s.total_return_pct) filter (where r.repo_change_pts > 0) as avg_return_hike_months_pct,
    avg(s.total_return_pct) filter (where r.repo_change_pts < 0) as avg_return_cut_months_pct,
    avg(s.total_return_pct) filter (where r.repo_change_pts = 0) as avg_return_hold_months_pct,
    -- The fitted change in a month's return for each 1-point change in the policy rate.
    regr_slope(s.total_return_pct, r.repo_change_pts) as return_per_rate_point_pct
from sector_months as s
inner join {{ ref('mart_rates_monthly') }} as r on r.month = s.month
group by s.sector
