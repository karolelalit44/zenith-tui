import pandas as pd
import io

raw_data = """id,name,category,price,stock,date
1,Widget A,Electronics,29.99,150,2026-01-01
2,Widget B,Electronics,49.99,80,2026-01-02
3,Gadget X,Home,15.50,200,2026-01-03
4,Gadget Y,Home,89.00,45,2026-01-04
5,Tool Z,Hardware,12.99,300,2026-01-05
"""
df = pd.read_csv(io.StringIO(raw_data))
df.to_csv("agg-bar-prism/data/raw_sales.csv", index=False)
print("Created sample csv")
