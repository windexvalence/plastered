#!/bin/sh

# Adopted from here: https://docs.github.com/en/actions/security-for-github-actions/security-guides/using-secrets-in-github-actions#limits-for-secrets

# --batch to prevent interactive command
# --yes to assume "yes" for questions
echo "Decrypting test HTML files ..."
for secret_file in secrets/mock_browser_html/*.gpg; do 
    out_filename=$(basename $secret_file | sed -nr 's/^(.*)\.gpg$/\1/p')
    out_filepath="tests/resources/mock_browser_html/$out_filename"
    echo "decrypting input file at '$secret_file' and writing output to '$out_filepath' ..."
    gpg --quiet \
        --batch \
        --yes \
        --decrypt \
        --passphrase="$TEST_HTML_PASSPHRASE" \
        --output "$out_filepath" "$secret_file"
done

echo "Decrypting test API response JSON files ..."
for secret_file in secrets/mock_api_responses/*.gpg; do 
    out_filename=$(basename $secret_file | sed -nr 's/^(.*)\.gpg$/\1/p')
    out_filepath="tests/resources/mock_api_responses/$out_filename"
    echo "decrypting input file at '$secret_file' and writing output to '$out_filepath' ..."
    gpg --quiet \
        --batch \
        --yes \
        --decrypt \
        --passphrase="$TEST_HTML_PASSPHRASE" \
        --output "$out_filepath" "$secret_file"
done
