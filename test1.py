import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv('./model_output/emg_features.csv')

features = ['rms', 'mav', 'var', 'peak', 'zcr', 'wl', 'mad']
fig, axes = plt.subplots(2, 4, figsize=(16, 6))
axes = axes.flatten()

for i, feat in enumerate(features):
    for user, grp in df.groupby('user_id'):
        axes[i].hist(grp[feat], bins=30, alpha=0.6, label=user)
    axes[i].set_title(feat)
    axes[i].legend()

plt.tight_layout()
plt.savefig('feature_distributions.png', dpi=120)
print('Saved feature_distributions.png')