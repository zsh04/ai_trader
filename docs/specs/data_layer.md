# Data Abstraction Layer (DAL)

This document defines the Data Abstraction Layer (DAL) for the project. The DAL is responsible for providing a unified interface for accessing data from various sources, initially supporting Tiingo and Marketstack.

## Design Goals

*   **Source Agnostic:** The rest of the application should not need to know which data source is being used.
*   **Extensibility:** Adding new data sources should be straightforward.
*   **Unified Data Format:** All data returned by the DAL should be in a consistent format.

## Integration with Tiingo and Marketstack

The DAL will have specific connectors for Tiingo and Marketstack. These connectors will be responsible for:

1.  **Authentication:** Handling API keys and other authentication mechanisms.
2.  **Data Fetching:** Making requests to the respective APIs.
3.  **Data Transformation:** Converting the data from the source-specific format to the unified DAL format.

## Unified Data Format

The DAL will return data in a standardized format. For example, stock price data will be returned as a list of objects, where each object has the following fields:

*   `timestamp`: The timestamp of the data point.
*   `open`: The opening price.
*   `high`: The highest price.
*   `low`: The lowest price.
*   `close`: The closing price.
*   `volume`: The trading volume.

This ensures that the application can process the data consistently, regardless of the source.
