package dev.reguard.safety.product;

import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

import java.util.*;

@Repository
public class ProductRepository {
    private final NamedParameterJdbcTemplate jdbc;

    public ProductRepository(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<Product> search(String query, String category, long offset, int limit) {
        String pattern = "%" + query.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%";
        var params = new HashMap<String, Object>();
        params.put("pattern", pattern);
        params.put("limit", limit);
        params.put("offset", offset);
        String categoryClause = "";

        if (category != null) {
            categoryClause = " AND p.category = :category";
            params.put("category", category);
        }
        var products =
                jdbc.query(
                        """
                        SELECT
                            p.id,
                            p.name,
                            p.company_name,
                            p.category,
                            p.model_name,
                            p.image_url
                        FROM products p
                        WHERE (p.name ILIKE :pattern ESCAPE '!'
                            OR p.company_name ILIKE :pattern ESCAPE '!'
                            OR p.model_name ILIKE :pattern ESCAPE '!'
                            OR EXISTS (SELECT 1 FROM product_identifiers i
                                WHERE i.product_id = p.id
                                AND i.identifier_value ILIKE :pattern ESCAPE '!'))
                        """
                                + categoryClause
                                + " ORDER BY p.name, p.id LIMIT :limit OFFSET :offset",
                        params,
                        (rs, row) ->
                                new Product(
                                        rs.getObject("id", UUID.class),
                                        rs.getString("name"),
                                        rs.getString("company_name"),
                                        rs.getString("category"),
                                        rs.getString("model_name"),
                                        rs.getString("image_url"),
                                        List.of()));

        return withIdentifiers(products);
    }

    public Optional<Product> findById(UUID productId) {
        var products =
                jdbc.query(
                        """
                        SELECT
                            id,
                            name,
                            company_name,
                            category,
                            model_name,
                            image_url
                        FROM products
                        WHERE id = :id
                        """,
                        Map.of("id", productId),
                        (rs, row) ->
                                new Product(
                                        rs.getObject("id", UUID.class),
                                        rs.getString("name"),
                                        rs.getString("company_name"),
                                        rs.getString("category"),
                                        rs.getString("model_name"),
                                        rs.getString("image_url"),
                                        List.of()));

        return withIdentifiers(products).stream().findFirst();
    }

    private List<Product> withIdentifiers(List<Product> products) {
        if (products.isEmpty()) {
            return products;
        }
        Map<UUID, List<Product.Identifier>> identifiers = new HashMap<>();
        jdbc.query(
                """
                SELECT
                    product_id,
                    identifier_type,
                    identifier_value
                FROM product_identifiers
                WHERE product_id IN (:ids) ORDER BY identifier_type, identifier_value
                """,
                Map.of("ids", products.stream().map(Product::id).toList()),
                rs -> {
                    identifiers
                            .computeIfAbsent(
                                    rs.getObject("product_id", UUID.class),
                                    key -> new ArrayList<>())
                            .add(
                                    new Product.Identifier(
                                            rs.getString("identifier_type"),
                                            rs.getString("identifier_value")));
                });

        Map<UUID, String> recallImages = new HashMap<>();
        jdbc.query(
                """
                SELECT m.product_id, min(r.image_url) AS image_url
                FROM recall_product_matches m JOIN recalls r ON r.id = m.recall_id
                WHERE m.product_id IN (:ids)
                  AND (m.match_status = 'CONFIRMED'
                    OR (m.match_method = 'KC_CERT_MODEL' AND m.rule_version IN ('kc-cert-model-v2', 'kc-cert-model-v3')))
                  AND nullif(btrim(r.image_url), '') IS NOT NULL
                GROUP BY m.product_id HAVING count(DISTINCT r.image_url) = 1
                """,
                Map.of("ids", products.stream().map(Product::id).toList()),
                rs -> { recallImages.put(rs.getObject("product_id", UUID.class), rs.getString("image_url")); });

        return products.stream()
                .map(
                        p ->
                                new Product(
                                        p.id(),
                                        p.name(),
                                        p.companyName(),
                                        p.category(),
                                        p.modelName(),
                                        p.imageUrl() == null || p.imageUrl().isBlank()
                                                ? recallImages.get(p.id()) : p.imageUrl(),
                                        List.copyOf(identifiers.getOrDefault(p.id(), List.of()))))
                .toList();
    }
}
