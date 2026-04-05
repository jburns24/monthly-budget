# 04 Questions Round 1 - Categories Management

## 1. Icon Format
**Q:** The PRD schema has an `icon` VARCHAR(50) field. What format should category icons use?
**A:** Emoji characters. Users pick an emoji (e.g. grocery cart, burger). Store raw emoji in VARCHAR(50). No icon library needed.

## 2. Default/Seed Categories
**Q:** Should Epic 4 include a seed/suggestion API for the 6 PRD-suggested defaults?
**A:** Yes, include a seed endpoint. POST /api/families/{id}/categories/seed that bulk-creates the 6 suggested defaults (Groceries, Dining, Transport, Entertainment, Bills, Other). Onboarding epic calls this.

## 3. Delete Behavior
**Q:** Should DELETE always soft-archive, or hard-delete when no expenses reference the category?
**A:** Hard-delete if no expenses reference the category. Archive (set is_active=false) if expenses exist, returning the CATEGORY_HAS_EXPENSES error code per PRD.

## 4. List API
**Q:** Should the list endpoint support sorting/filtering or just return all active?
**A:** Simple: return all active categories ordered by sort_order, then name. No query params needed for MVP.
