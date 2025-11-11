# 🧩 MongoDB Aggregation Pipeline Notes

## 📖 Overview
MongoDB aggregation pipelines transform and analyze data step-by-step, like SQL queries with joins, filters, and computed fields.

---

## 🧱 Common Pipeline Stages

| Stage | Description | Example |
|--------|--------------|----------|
| `$match` | Filters documents (like WHERE) | `{ "$match": { "status": "active" } }` |
| `$addFields` | Adds or modifies fields | `{ "$addFields": { "ageGroup": { "$cond": { "if": { "$gte": ["$age", 18] }, "then": "Adult", "else": "Minor" } } } }` |
| `$project` | Chooses what fields to return | `{ "$project": { "name": 1, "age": 1 } }` |
| `$lookup` | Joins two collections | `{ "$lookup": { "from": "users", "localField": "user_id", "foreignField": "_id", "as": "user" } }` |
| `$unwind` | Deconstructs array fields | `{ "$unwind": { "path": "$user", "preserveNullAndEmptyArrays": true } }` |
| `$sort` | Sorts documents | `{ "$sort": { "date": -1 } }` |

---

## ⚙️ Common Expressions

| Operator | Purpose | Example |
|-----------|----------|----------|
| `$cond` | Conditional (if-then-else) | `{ "$cond": { "if": { "$gt": ["$age", 18] }, "then": "Adult", "else": "Minor" } }` |
| `$and`, `$or`, `$not` | Logic | `{ "$and": [ { "$eq": ["$type", "income"] }, { "$gt": ["$amount", 100] } ] }` |
| `$toObjectId` | Convert to ObjectId | `{ "$toObjectId": "$category_id" }` |
| `$toString` | Convert to string | `{ "$toString": "$_id" }` |
| `$ifNull` | Fallback if null | `{ "$ifNull": ["$category_name", "Others"] }` |
| `$ne`, `$eq`, `$gt`, `$lt` | Comparisons | `{ "$ne": ["$field", ""] }` |

---

## 🧠 Key Tips When Writing Pipelines

1. Every stage starts with `$` → `{ "$match": { ... } }`
2. Stages go **inside an array** `[ {...}, {...} ]`
3. Expressions inside stages also start with `$`
4. Use `{}` for objects and `[]` for arrays
5. Order matters! `$match` early → `$project` late
6. `$cond` = if/else logic
7. `$lookup` = SQL join
8. `$unwind` = flatten array results
9. `$project` = shape your output
10. Test each stage in MongoDB Compass or shell

---

## 📘 Example Pipeline Reference

```python
pipeline = [
    {"$match": {"user_id": user_id}},
    {"$addFields": {
        "category_object_id": {
            "$cond": {
                "if": {"$and": [
                    {"$ne": ["$category_id", ""]},
                    {"$ne": ["$category_id", None]}
                ]},
                "then": {"$toObjectId": "$category_id"},
                "else": None
            }
        }
    }},
    {"$lookup": {
        "from": "categories",
        "localField": "category_object_id",
        "foreignField": "_id",
        "as": "category"
    }},
    {"$unwind": {"path": "$category", "preserveNullAndEmptyArrays": True}},
    {"$project": {
        "_id": {"$toString": "$_id"},
        "category_name": {"$ifNull": ["$category.category_name", "Others"]}
    }},
    {"$sort": {"date": -1}}
]
