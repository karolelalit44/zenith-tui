const fs = require('fs');
const path = require('path');

const srcDir = path.join(__dirname, 'src');

const replacements = {
  'theme.colors.text.primary': 'theme.colors.text.ethereal',
  'theme.colors.text.accentOrange': 'theme.colors.text.emerald',
  'theme.colors.text.accentPurple': 'theme.colors.text.warning',
  'theme.colors.text.accentBlue': 'theme.colors.text.emerald' // Fallback for active state
};

function walk(dir) {
  let results = [];
  const list = fs.readdirSync(dir);
  list.forEach(file => {
    file = path.join(dir, file);
    const stat = fs.statSync(file);
    if (stat && stat.isDirectory()) {
      results = results.concat(walk(file));
    } else if (file.endsWith('.tsx') || file.endsWith('.ts')) {
      results.push(file);
    }
  });
  return results;
}

const files = walk(srcDir);
files.forEach(file => {
  let content = fs.readFileSync(file, 'utf8');
  let original = content;
  
  for (const [oldToken, newToken] of Object.entries(replacements)) {
    content = content.split(oldToken).join(newToken);
  }
  
  if (content !== original) {
    fs.writeFileSync(file, content, 'utf8');
    console.log(`Updated tokens in: ${file}`);
  }
});
