#pragma once
#include <cstdint>
namespace esphome::matter {
class MatterEndpointMappingBase {
 public:
  explicit MatterEndpointMappingBase(uint16_t endpoint) : endpoint_(endpoint) {}
  virtual ~MatterEndpointMappingBase() = default;
  virtual bool validate() { return true; }
  virtual void initialize() {}
  uint16_t endpoint_id() const { return endpoint_; }

 private:
  uint16_t endpoint_;
};
}  // namespace esphome::matter
