-- What classifying the articles cost, by the tier that decided.
select
    decided_by,
    count(*)                                   as articles,
    round(sum(cost_eur), 4)                    as cost_eur,
    round(avg(cost_eur), 6)                    as cost_per_article_eur,
    round(avg(confidence), 3)                  as mean_confidence
from {{ source('core', 'article') }}
group by decided_by
