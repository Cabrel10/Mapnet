FROM golang:1.22-bookworm AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o /out/map-engine ./cmd/map-engine

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=build /out/map-engine /map-engine
EXPOSE 8082
USER nonroot:nonroot
ENTRYPOINT ["/map-engine"]
