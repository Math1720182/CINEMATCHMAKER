# About

**CineMatchMaker** is an interactive web application built with **Python** and **Streamlit** that helps users find the perfect movie based on their preferences and users like them.

## Key Features

- **Movie Matching:** Personalized recommendations tailored to your favorite genres, actors, or directors.
- **Login page:** Connect with Google OAuth2.0 or create an account with the form.
- **My movies:** Add your favorite movies to save your watchlist and improve your recommendation algorithm.
- **Advanced Search & Filters:** Filter options by streaming platform (Netflix, Prime Video, Disney+, etc.).
- **Trends & Insights:** Discover top-trending movies and popular titles in real-time.
- **AI chat-bot:** Ask Tomy, your personal AI assistant about movies!

---

## Tech Stack

- **Frontend / UI:** [Streamlit](https://streamlit.io/)
- **Language:** Python 3.14
- **Data Processing:** Pandas, NumPy, Scikit-learn, Pytorch
- **Data Source / API:** The Movie Database (TMDb) API, MovieLens 32M Database
- **AI:** Google GenAI - Gemini 3.5 Flash-Lite
- **Encryption:** bcrypt, uuid

*See all extensions in requirements.txt*

---

## Project Structure

```
CineMatchMaker/
├── run_app.py          # Main Streamlit application
├── data/               # Datasets (movies, shows, ratings etc.)
├── pages/              # Pages of the app
├── utils/              # Recommendation logic and API helpers
├── .streamlit/         # Custom Streamlit configuration & theme
├── requirements.txt    # Project dependencies
└── README.md           # Documentation
```

---

# Recommendation Engine Architecture

CineMatchMaker employs a sophisticated hybrid recommendation system combining linear algebra, content-based filtering, and deep learning techniques to deliver highly dynamic and personalized movie suggestions.

### 1. Two-Tower Neural Collaborative Filtering (NCF) Architecture

To capture complex latent interactions between users and items, I trained a **Two-Tower Neural Collaborative Filtering (NCF)** model.

```
       User Index                        Movie Index
           │                                 │
   ┌───────┴────────┐                ┌───────┴────────┐
   │ User Embedding │                │ Item Embedding │
   │ Tower (E_u)    │                │ Tower (E_i)    │
   └───────┬────────┘                └───────┬────────┘
           │ (dim = 64)                      │ (dim = 64)
           └──────────────┬──────────────────┘
                          │
                   Dot Product / MLP
                          │
                     Predicted
                     Rating r̂
```

- **User Tower:** Maps a discrete user ID $u$ to a dense embedding vector $E_u \in \mathbb{R}^{d}$ (where $d = 64$).
- **Item Tower:** Maps a discrete movie ID $i$ to a dense embedding vector $E_i \in \mathbb{R}^{d}$.
- **Loss Function:** Trained using Mean Squared Error (MSE) loss against explicit user ratings $r_{u,i}$:

$$
\mathcal{L} = \frac{1}{N} \sum_{u,i} \left( r_{u,i} - \hat{r}_{u,i} \right)^2
$$

### Model Training Implementation

The model was trained for 20 epochs using the **Adam optimizer** ($\text{learning rate} = 0.001$) and dynamic mini-batching ($\text{batch size} = 1024$).

```python
# Model initialization and loss setup
model = TwoTowerNCF(num_users, num_items, embedding_dim=64).to(device)
criterion = nn.MSELoss()
optimizer = torch.optim.Adam(model.parameters(), lr=0.001)

# Extracted training step loop
for epoch in range(epochs):
    model.train()
    for i in range(0, num_samples_train, batch_size):
        optimizer.zero_grad()
        indices = permutation_train[i : i + batch_size]

        predictions = model(batch_users[indices], batch_items[indices])
        loss = criterion(predictions, batch_ratings[indices])

        loss.backward()
        optimizer.step()
```

*Note: Model convergence plateaued at **20 epochs** before validation MSE began to overfit.*

Once trained, I extracted the learned item embedding weights $V \in \mathbb{R}^{M \times 64}$ (where $M$ is the total number of items) and exported them to disk (`movie_embeddings.npy`) for lightweight real-time linear algebra inference.

---

## 2. On-the-Fly User Vector Construction via Linear Algebra

At inference time in Streamlit, rather than running a full forward pass through PyTorch for every user input, I compute user representations using matrix operations in NumPy.

Given a user’s logged ratings $\{r_1, r_2, \dots, r_k\}$ for movies $\{i_1, i_2, \dots, i_k\}$:

1. **Center Ratings (Weight Assignment):**
Ratings are normalized around a baseline score of $3.0$:
    
$$
w_k = r_k - 3.0
$$
    
    - A rating of $5.0$ yields a positive weight $+2.0$.
    - A rating of $1.0$ yields a negative weight $-2.0$.
2. **User Profile Matrix Multiplication:**
Let $W \in \mathbb{R}^{1 \times k}$ be the row vector of user weights, and $V_{watched} \in \mathbb{R}^{k \times 64}$ be the embedding matrix of the $k$ watched movies:
    
$$
U_{profile} = W \cdot V_{watched} = \sum_{j=1}^{k} w_j \mathbf{e}_{i_j}
$$
    
    Where $U_{profile} \in \mathbb{R}^{1 \times 64}$ represents the aggregated user preference in latent vector space.
    
3. **Cosine Similarity Match against Catalog:**
I compute the Cosine Similarity between the user vector $U_{profile}$ and all candidate movie embeddings $V_i \in V$:
    
    $$
    \text{Sim}(U_{profile}, V_i) = \frac{U_{profile} \cdot V_i^\top}{\|U_{profile}\|_2 \|V_i\|_2}
    $$
    
4. **Filtering and Ranking:**
Previously watched movie indices are set to $-\infty$ so they are omitted, and the catalog is ranked by descending similarity score:
    
    $$
    \text{Top Movies} = \operatorname{argsort}\left(\text{Sim}(U_{profile}, V)\right)[::-1]
    $$
    

---

## 3. Cold Start Strategy

When a user interacts with or rates a movie $m_{new}$ that was not present in the original training split or dataset matrix, I execute a content-based fallback mechanism:

```
                  Unseen / New Movie
                          │
             Genre Filter & TF-IDF Vector
                          │
           Cosine Similarity (Feature Space)
                          │
             Nearest Catalog Movie Index
                          │
          Incorporate into Latent Projection
```

1. **Genre Feature Filtering:** Filter the reference catalog by matching genre criteria.
2. **Feature Cosine Similarity:** Compute cosine similarity over the high-dimensional feature representations ($D$) between the new movie vector $\mathbf{v}_{new}$ and catalog movie vectors $\mathbf{v}_c$:
    
    $$
    \text{Sim}_{\text{content}}(\mathbf{v}_{new}, \mathbf{v}_c) = \frac{\mathbf{v}_{new} \cdot \mathbf{v}_c^\top}{\|\mathbf{v}_{new}\|_2 \|\mathbf{v}_c\|_2}
    $$
    
3. **Embedding Substitution:** Select the nearest catalog neighbor index $i_{nearest} = \arg\max (\text{Sim}_{\text{content}})$ and substitute its learned embedding vector $E_{i_{nearest}}$ into the user profiling matrix calculation.

---

## License

This project is open-source and available under the AGPL-3.0 license.
