WORK-BRAIN-DOMAIN-TAGS v1

# Work Brain Domain Tags

`domain_tags` are unbounded retrieval labels for the subject matter and
capabilities materially supported by a Work Brain conversation. They are not a
closed enum and they are separate from the one-or-two domain probes used to
control conversation context.

## Assignment procedure

1. Extract concrete terms from the user's words and supplied evidence.
2. Add the broad area and each materially distinct subtopic when both improve
   future retrieval.
3. Add demonstrated capabilities relevant to later retrieval, especially for
   interview stories: `ownership`, `decision-making`, `influence`,
   `stakeholder-management`, `execution`, `trade-offs`, `outcomes`, and
   `learning`.
4. Do not add a tag solely because it appears in an interview question, a probe,
   or a flattering interpretation of the story.
5. Normalize tags to lowercase hyphenated tokens. There is no count limit, but
   every tag should be supported and should improve a plausible future search.

## Starter vocabulary

The vocabulary is extensible. Reuse these spellings where they fit; do not
force unrelated work into them.

- Business and founder: `business`, `founder`, `strategy`, `pricing`,
  `distribution`, `customer`, `sales`, `fundraising`, `operations`.
- Engineering and technical: `engineering`, `architecture`, `debugging`,
  `security`, `reliability`, `migration`, `observability`, `performance`,
  `infrastructure`, `api`, `data`.
- Identity and access: `identity`, `authentication`, `login`,
  `authorization`, `access-control`, `session-management`, `oauth`, `sso`,
  `mfa`, `passwords`, `api-security`, `secrets`.
- Product and market: `product`, `customer`, `discovery`, `prioritization`,
  `adoption`, `marketing`, `positioning`, `launch`.
- People and leadership: `leadership`, `people-management`, `hiring`,
  `delegation`, `coaching`, `conflict`, `influence`, `communication`.
- Interview-relevant capabilities: `ambiguity`, `decision-making`, `ownership`,
  `execution`, `trade-offs`, `evidence`, `outcomes`, `learning`.

Keep materially distinct technical concepts separate. For example, an access
flow may deserve `security`, `authentication`, `login`, `authorization`, and
`access-control` when each is actually discussed. Do not add every related
term automatically: `authentication` does not by itself prove `oauth`, `sso`,
or `mfa`.

Question-bank tags such as `official-question` and `meta` remain question-bank
metadata. They become evidence tags only when the user's experience supports
the same meaning.
