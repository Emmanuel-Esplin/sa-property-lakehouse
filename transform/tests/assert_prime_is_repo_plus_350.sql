-- South African banks set prime at the policy rate plus 3.5 points. In the SARB data that holds
-- on every day since August 2004, so a break means the data or the month-end logic is wrong.
select month, repo_rate_pct, prime_rate_pct
from {{ ref('mart_rates_monthly') }}
where month >= date '2005-01-01'
    and abs(prime_rate_pct - repo_rate_pct - 3.5) > 1e-9
