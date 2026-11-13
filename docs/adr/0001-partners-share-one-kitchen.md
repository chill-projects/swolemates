# Linked partners share one Kitchen

Everything else in Swolemates belongs to one user, and partners only see each other's aggregates. The Kitchen is the deliberate exception: linked partners read and write a single shared Kitchen, because there is one physical fridge and two separate lists would stop agreeing after the second shop. This is allowed because the Kitchen records what is in the house, not what anyone ate. Food logs, meal plans and saved meals stay private to each person.

## Considered Options

- **Separate Kitchens, each person logs their own hauls:** keeps the per-user rule intact, but neither list reflects what's actually at home.
- **Separate Kitchens, readable by the partner:** answers "do we have milk?" only by checking two lists, and neither person can correct the other's.

## Consequences

- "Every query filters by `user_id`" no longer describes Kitchen queries, which have to resolve to the caller's shared Kitchen. The permission check still belongs in the service layer.
- Linking two people merges their existing Kitchens. If unlinking is ever added, each person gets a copy.
- A Leftover's macros are visible to the partner. We accept this: a Leftover in the fridge isn't a food log.
- Anything that follows a Kitchen Item across users has to cover both partners. For example, removing a Leftover must protect the macros on either person's plans, not just the remover's.
- Links from Kitchen Items to saved meals are removed, because saved meals are private to each person and a shared link would expose them to the partner.
