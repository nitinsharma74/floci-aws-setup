# OpenSearch Movie Search Service

## 1. Overview

The OpenSearch Movie Search Service is a serverless backend designed to provide low-latency movie search and search-as-you-type suggestions for a streaming application.

The project is being developed and tested locally using Floci.

The service will use a MovieLens dataset stored in Amazon S3. An ingestion Lambda will process the dataset and index movie records into Amazon OpenSearch.

A search Lambda will query OpenSearch and return ranked movie results to clients through an API.

The target architecture is:

```mermaid
flowchart LR
    A[MovieLens Dataset] --> B[Amazon S3]
    B --> C[Ingestion Lambda]
    C --> D[Amazon OpenSearch]

    E[Client / App] --> F[API Gateway]
    F --> G[Search Lambda]
    G --> D
    D --> G
    G --> F
    F --> E
```

The main ingestion flow is:

```text
MovieLens Dataset
        ↓
    Amazon S3
        ↓
Ingestion Lambda
        ↓
Amazon OpenSearch
```

The main search flow is:

```text
Client
  ↓
API Gateway
  ↓
Search Lambda
  ↓
Amazon OpenSearch
  ↓
Search Results
```

The initial search functionality will focus on movie titles and genres.

The service will eventually support search-as-you-type behavior, where suggestions are returned continuously as the user enters a movie title.

For example:

```text
I
↓
Inception
Interstellar
Inside Out

Inc
↓
Inception
Incendies

Incep
↓
Inception
```

The same movie dataset will later be reused to explore recommendation systems and personalized search.

---

## 2. Goals

WIP

---

## 3. Architecture

WIP

---

## 4. Movie Dataset

WIP

---

## 5. Amazon S3

WIP

---

## 6. Ingestion Lambda

WIP

---

## 7. Amazon OpenSearch

WIP

---

## 8. Search Lambda

WIP

---

## 9. API Gateway

WIP

---

## 10. Autocomplete

WIP

---

## 11. Running Locally with Floci

WIP

---

## 12. Testing

WIP

---

## 13. Performance and Scaling

WIP

---

## 14. Recommendation Engine

WIP

---

## 15. Future Improvements

WIP