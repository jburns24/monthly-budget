# Bulk monthly goals are upsert-only

Setting or updating Monthly Goals via `PUT /families/{id}/goals` used to treat any category omitted from the payload as a delete for that month. That made single-category “Set Goal” wipe sibling goals and made blank fields in Manage All Goals a silent remove. We changed bulk upsert to create/update only the listed categories and leave others alone; removals go through `DELETE /families/{id}/goals/{goal_id}` (Edit Goal → Remove).

**Considered options:** keep replace-all and have the frontend re-send every goal; add a separate create endpoint; upsert-only bulk (chosen — one server rule matches retention and blank-as-skip without a new route).
